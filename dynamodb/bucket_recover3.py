import re
import boto3
import pandas as pd
from urllib.parse import urlparse, unquote
from botocore.exceptions import ClientError

INPUT_CSV = "archivo_paths.csv"              # <-- tu archivo
INPUT_COLUMN = "PATH_ADUNTO"                 # <-- columna donde vienen las URLs
OUTPUT_CSV = "resultado_existencia_s3.csv"   # <-- salida


S3_HOST_PATTERN = re.compile(r"^(?P<bucket>[^.]+)\.s3\.(?P<region>[^.]+)\.amazonaws\.com$")


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
      - ("EXISTS", info) si HEAD OK
      - ("NOT_FOUND", None) si 404/NoSuchKey
      - ("ACCESS_DENIED", None) si 403
    """
    try:
        resp = s3.head_object(Bucket=bucket, Key=key)
        info = {
            "content_length": resp.get("ContentLength"),
            "last_modified": resp.get("LastModified"),
            "etag": resp.get("ETag"),
        }
        return "EXISTS", info
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            return "NOT_FOUND", None
        if code in ("403", "AccessDenied"):
            return "ACCESS_DENIED", None
        raise


def latest_state_via_versions(s3, bucket: str, key: str):
    """
    Usa versioning para determinar el estado "actual" (último evento):
      - ("DELETE_MARKED", timestamp) si el último evento es delete marker
      - ("HAS_VERSIONS", timestamp) si hay versiones y el último evento es una versión normal
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
            events.append(("DELETE_MARKER", dm.get("LastModified"), dm.get("VersionId")))

    for v in resp.get("Versions", []) or []:
        if v.get("Key") == key:
            events.append(("VERSION", v.get("LastModified"), v.get("VersionId")))

    if not events:
        return "NO_TRACE", None

    # evento más reciente = estado actual
    events.sort(key=lambda x: x[1], reverse=True)
    latest_type, latest_time, _ = events[0]

    if latest_type == "DELETE_MARKER":
        return "DELETE_MARKED", latest_time
    return "HAS_VERSIONS", latest_time


def check_one_url(url: str):
    url = (url or "").strip()
    if not url or not is_valid_s3_https_url(url):
        return {
            "url": url,
            "status": "INVALID_URL",
            "bucket": None,
            "region": None,
            "key": None,
            "details": None,
        }

    bucket, region, key = parse_s3_https_url(url)
    s3 = get_s3_client(region)

    status, info = head_exists(s3, bucket, key)

    if status == "EXISTS":
        return {
            "url": url,
            "status": "EXISTS",
            "bucket": bucket,
            "region": region,
            "key": key,
            "details": f"size={info.get('content_length')} last_modified={info.get('last_modified')} etag={info.get('etag')}",
        }

    if status == "ACCESS_DENIED":
        # Intentamos igual con versioning si permite listar
        v_status, v_time = latest_state_via_versions(s3, bucket, key)
        if v_status == "DELETE_MARKED":
            return {
                "url": url,
                "status": "DELETE_MARKED",
                "bucket": bucket,
                "region": region,
                "key": key,
                "details": f"latest_event={v_time} (HEAD denied)",
            }
        if v_status == "HAS_VERSIONS":
            return {
                "url": url,
                "status": "HAS_VERSIONS",
                "bucket": bucket,
                "region": region,
                "key": key,
                "details": f"latest_event={v_time} (HEAD denied)",
            }
        if v_status == "NO_TRACE":
            return {
                "url": url,
                "status": "NOT_FOUND",
                "bucket": bucket,
                "region": region,
                "key": key,
                "details": "no trace (HEAD denied)",
            }
        return {
            "url": url,
            "status": "ACCESS_DENIED",
            "bucket": bucket,
            "region": region,
            "key": key,
            "details": "denied for HEAD and list versions",
        }

    # status == NOT_FOUND por HEAD => buscamos si está borrado (delete marker) o si hay versiones
    v_status, v_time = latest_state_via_versions(s3, bucket, key)

    if v_status == "DELETE_MARKED":
        return {
            "url": url,
            "status": "DELETE_MARKED",
            "bucket": bucket,
            "region": region,
            "key": key,
            "details": f"latest_delete_marker={v_time}",
        }

    if v_status == "HAS_VERSIONS":
        # Raro si HEAD dio 404, pero lo dejamos por robustez
        return {
            "url": url,
            "status": "HAS_VERSIONS",
            "bucket": bucket,
            "region": region,
            "key": key,
            "details": f"latest_version_event={v_time}",
        }

    if v_status == "ACCESS_DENIED":
        return {
            "url": url,
            "status": "ACCESS_DENIED",
            "bucket": bucket,
            "region": region,
            "key": key,
            "details": "no permission to list versions",
        }

    return {
        "url": url,
        "status": "NOT_FOUND",
        "bucket": bucket,
        "region": region,
        "key": key,
        "details": "no trace (no head, no versions)",
    }


def main():
    df = pd.read_csv(INPUT_CSV)

    if INPUT_COLUMN not in df.columns:
        raise ValueError(f"No existe la columna '{INPUT_COLUMN}' en {INPUT_CSV}. Columnas: {list(df.columns)}")

    results = []
    for i, url in enumerate(df[INPUT_COLUMN].tolist(), start=1):
        r = check_one_url(str(url) if not pd.isna(url) else "")
        results.append(r)
        print(f"[{i}] {r['status']}  ->  {r['url']}")

    out = pd.DataFrame(results)
    out.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")

    print("\n--- RESUMEN ---")
    print(out["status"].value_counts(dropna=False))
    print(f"\n✅ Archivo generado: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
