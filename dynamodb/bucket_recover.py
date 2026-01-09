import re
import boto3
from botocore.exceptions import ClientError
from urllib.parse import urlparse, unquote


def parse_s3_https_url(url: str):
    """
    Soporta URLs tipo:
    https://<bucket>.s3.<region>.amazonaws.com/<key>
    """
    parsed = urlparse(url)
    host = parsed.netloc  # miu-documentos.s3.us-west-2.amazonaws.com
    path = unquote(parsed.path.lstrip("/"))  # key

    m = re.match(r"^(?P<bucket>[^.]+)\.s3\.(?P<region>[^.]+)\.amazonaws\.com$", host)
    if not m:
        raise ValueError(f"URL no soportada: {url}")

    return m.group("bucket"), m.group("region"), path


def s3_object_exists(bucket: str, key: str, region: str):
    s3 = boto3.client("s3", region_name=region)

    try:
        resp = s3.head_object(Bucket=bucket, Key=key)
        return True, {
            "status": "exists",
            "content_length": resp.get("ContentLength"),
            "last_modified": resp.get("LastModified"),
            "etag": resp.get("ETag"),
        }
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            return False, {"status": "not_found"}
        if code in ("403", "AccessDenied"):
            # Puede existir pero no tienes permiso, o la política bloquea HEAD
            return None, {"status": "unknown_access_denied"}
        raise


def s3_is_delete_marked(bucket: str, key: str, region: str):
    """
    Si el bucket tiene versioning, esto detecta si el 'estado actual' es delete marker.
    - Si el primer resultado al listar versiones es un DeleteMarker=True, significa que está "borrado" actualmente.
    """
    s3 = boto3.client("s3", region_name=region)

    resp = s3.list_object_versions(Bucket=bucket, Prefix=key)
    candidates = []

    # Delete markers
    for dm in resp.get("DeleteMarkers", []):
        if dm.get("Key") == key:
            candidates.append(("delete_marker", dm.get("LastModified")))

    # Versiones
    for v in resp.get("Versions", []):
        if v.get("Key") == key:
            candidates.append(("version", v.get("LastModified")))

    if not candidates:
        return None  # no hay rastro (o no tienes permiso)

    # El "estado actual" es el más reciente por LastModified
    candidates.sort(key=lambda x: x[1], reverse=True)
    latest_type, latest_time = candidates[0]
    return latest_type == "delete_marker", latest_time


def main(url: str):
    bucket, region, key = parse_s3_https_url(url)

    print("Bucket:", bucket)
    print("Region:", region)
    print("Key   :", key)
    print("-" * 60)

    exists, info = s3_object_exists(bucket, key, region)

    if exists is True:
        print("✅ EXISTE (HEAD OK)")
        print(info)
        return

    if exists is False:
        print("❌ NO EXISTE (NoSuchKey/404)")
        # Si tiene versioning, puede estar “borrado” con delete marker:
        try:
            dm, ts = s3_is_delete_marked(bucket, key, region)
            if dm is True:
                print(f"🟡 PERO: el objeto parece estar 'borrado' por Delete Marker (último evento: {ts})")
            elif dm is False:
                print(f"🟡 Hay versiones, pero el estado actual no es delete marker (último evento: {ts})")
            else:
                print("ℹ️ No se encontraron versiones (o no hay permisos para listarlas).")
        except ClientError as e:
            print("ℹ️ No pude verificar versioning (permisos/política):", e.response["Error"]["Code"])
        return

    # exists is None => AccessDenied
    print("⚠️ No puedo confirmar con HEAD (AccessDenied). Puede existir, pero no tienes permiso para HEAD.")
    # Intentamos igual con versioning (si tienes permiso)
    try:
        dm, ts = s3_is_delete_marked(bucket, key, region)
        if dm is True:
            print(f"🟡 Parece estar 'borrado' por Delete Marker (último evento: {ts})")
        elif dm is False:
            print(f"✅ Hay versiones del objeto (último evento: {ts})")
        else:
            print("ℹ️ No se encontró rastro (o no hay permisos).")
    except ClientError as e:
        print("ℹ️ Tampoco pude listar versiones:", e.response["Error"]["Code"])


if __name__ == "__main__":
    test_url = "https://miu-documentos.s3.us-west-2.amazonaws.com/DATA-DOCS/miu-hml/documentos/143720/23820040/miuDocumento_997018_duplica.AD.JeffHardinGregoryBertoni-Becker_sWorldoftheCell-Pearson2018.pdf"
    main(test_url)

