import re
import boto3
from botocore.exceptions import ClientError
from urllib.parse import urlparse, unquote


def is_valid_s3_https_url(url: str) -> bool:
    try:
        parsed = urlparse(url)

        if parsed.scheme != "https":
            return False

        if not parsed.netloc or not parsed.path:
            return False

        # Valida dominio S3 estándar
        s3_pattern = r"^[^\.]+\.s3\.[^\.]+\.amazonaws\.com$"
        if not re.match(s3_pattern, parsed.netloc):
            return False

        # Debe existir una key (no solo "/")
        if parsed.path == "/" or parsed.path.strip() == "":
            return False

        return True
    except Exception:
        return False


def parse_s3_https_url(url: str):
    parsed = urlparse(url)
    host = parsed.netloc
    path = unquote(parsed.path.lstrip("/"))

    m = re.match(
        r"^(?P<bucket>[^.]+)\.s3\.(?P<region>[^.]+)\.amazonaws\.com$",
        host
    )
    if not m:
        raise ValueError("Formato de URL S3 no soportado")

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
            return None, {"status": "access_denied"}
        raise


def s3_is_delete_marked(bucket: str, key: str, region: str):
    s3 = boto3.client("s3", region_name=region)

    resp = s3.list_object_versions(Bucket=bucket, Prefix=key)
    events = []

    for dm in resp.get("DeleteMarkers", []):
        if dm.get("Key") == key:
            events.append(("delete_marker", dm["LastModified"]))

    for v in resp.get("Versions", []):
        if v.get("Key") == key:
            events.append(("version", v["LastModified"]))

    if not events:
        return None, None

    events.sort(key=lambda x: x[1], reverse=True)
    return events[0][0] == "delete_marker", events[0][1]


def main(url: str):
    bucket, region, key = parse_s3_https_url(url)

    print("Bucket:", bucket)
    print("Region:", region)
    print("Key   :", key)
    print("-" * 60)

    exists, info = s3_object_exists(bucket, key, region)

    if exists is True:
        print("✅ EXISTE")
        print(info)
        return

    if exists is False:
        print("❌ NO EXISTE")
        dm, ts = s3_is_delete_marked(bucket, key, region)
        if dm is True:
            print(f"🟡 Está borrado por Delete Marker (último evento: {ts})")
        elif dm is False:
            print(f"🟡 Existen versiones (último evento: {ts})")
        else:
            print("ℹ️ No se encontraron versiones")
        return

    print("⚠️ Acceso denegado para validar con HEAD")


if __name__ == "__main__":
    test_url = "https://miu-documentos.s3.us-west-2.amazonaws.com/DATA-DOCS/miu-hml/documentos/143720/23820040/miuDocumento_997018_duplica.AD.JeffHardinGregoryBertoni-Becker_sWorldoftheCell-Pearson2018.pdf"

    if not is_valid_s3_https_url(test_url):
        print("❌ URL inválida o no es una URL S3 válida")
    else:
        main(test_url)
