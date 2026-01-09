import re
import boto3
import pandas as pd
from urllib.parse import urlparse, unquote
from botocore.exceptions import ClientError

INPUT_CSV = "archivo_paths.csv"                 # <-- tu archivo
INPUT_COLUMN = "PATH_ADUNTO"                    # <-- columna con URLs
OUTPUT_CSV = "solo_delete_marked.csv"           # <-- salida (solo delete_marked)

S3_HOST_PATTERN = re.compile(
    r"^(?P<bucket>[^.]+)\.s3\.(?P<region>[^.]+)\.amazonaws\.com$"
)

def is_valid_s3_https_url(url: str) -> bool:
    try:
        p = urlparse(url)
        if p.scheme != "https":
            return False
        if not p.netloc or not p.path or p.path == "/":
            return False
        return S3_HOST_PATTERN.match(p.netloc) is not None
    except Exception:
        return False

def parse_s3_https_url(url: str):
    p = urlparse(url)
    host = p.netloc
    key = unquote(p.path.lstrip("/"))
    m = S3_HOST_PATTERN.match(host)
    if not m:
        raise ValueError("Formato de URL S3 no soportado")
    return m.group("bucket"), m.group("region"), key

def get_s3_client(region: str):
    return boto3.client("s3", region_name=region)

def head_exists(s3, bucket: str, key: str):
    """
    Retorna:
      - "EXISTS" si HEAD OK
      - "NOT_FOUND" si 404/NoSuchKey
      - "ACCESS_DENIED" si 403
    """
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return "EXISTS"
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            return "NOT_FOUND"
        if code in ("403", "AccessDenied"):
            return "ACCESS_DENIED"
        raise

def latest_state_via_versions(s3, bucket: str, key: str):
    """
    Retorna:
      - ("DELETE_MARKED", timestamp) si el último evento es delete marker
      - ("HAS_VERSIONS", timestamp) si hay versiones y el último evento es versión
      - ("NO_TRACE", None) si no hay rastro
      - ("ACCESS_DENIED", None) si no hay permisos
    """
    try:
        resp = s3.list_object_versions(Bucket=bucket, Prefix=key)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("403", "AccessDenied"):
            return "ACCESS_DENIED", None
        raise

    events = []

    for dm in resp.get("DeleteMarkers", []) or []:
        if dm.get("Key") == key:
            events.append(("DELETE_MARKER", dm.get("LastModified")))

    for v in resp.get("Versions", []) or []:
        if v.get("Key") == key:
            events.append(("VERSION", v.get("LastModified")))

    if not events:
        return "NO_TRACE", None

    events.sort(key=lambda x: x[1], reverse=True)
    latest_type, latest_time = events[0]

    if latest_type == "DELETE_MARKER":
        return "DELETE_MARKED", latest_time
    return "HAS_VERSIONS", latest_time

def check_delete_marked(url: str):
    url = (url or "").strip()
    if not url or not is_valid_s3_https_url(url):
        return None  # ignoramos inválidas

    bucket, region, key = parse_s3_https_url(url)
    s3 = get_s3_client(region)

    head_status = head_exists(s3, bucket, key)

    # Si existe normal, NO lo devolvemos
    if head_status == "EXISTS":
        return None

    # Si no existe o no podemos confirmar, buscamos estado por versiones
    v_status, v_time = latest_state_via_versions(s3, bucket, key)

    if v_status == "DELETE_MARKED":
        return {
            "s3_path": f"s3://{bucket}/{key}",
            "bucket": bucket,
            "key": key,
            "region": region,
            "url": url,
            "latest_delete_marker": str(v_time),
        }

    # Si no es delete marked, NO lo devolvemos (NOT_FOUND / HAS_VERSIONS / ACCESS_DENIED / etc.)
    return None

def main():
    df = pd.read_csv(INPUT_CSV)

    if INPUT_COLUMN not in df.columns:
        raise ValueError(
            f"No existe la columna '{INPUT_COLUMN}' en {INPUT_CSV}. Columnas: {list(df.columns)}"
        )

    rows_out = []
    urls = df[INPUT_COLUMN].tolist()

    for i, raw in enumerate(urls, start=1):
        url = "" if pd.isna(raw) else str(raw)
        result = check_delete_marked(url)
        if result:
            rows_out.append(result)
            print(f"[{i}] ✅ DELETE_MARKED -> {result['s3_path']}")
        else:
            print(f"[{i}] (skip)")

    out = pd.DataFrame(rows_out, columns=["s3_path", "bucket", "key", "region", "url", "latest_delete_marker"])
    out.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")

    print("\n--- LISTO ---")
    print(f"Total DELETE_MARKED encontrados: {len(rows_out)}")
    print(f"✅ Archivo generado: {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
