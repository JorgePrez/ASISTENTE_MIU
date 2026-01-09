import boto3
import pandas as pd
from botocore.exceptions import ClientError

INPUT_CSV = "solo_delete_marked.csv"     # <- el que generaste antes
OUTPUT_PREVIEW_CSV = "preview_restore.csv"

DRY_RUN = True  # True = solo muestra/preview, False = borra delete markers (restaura)

def parse_s3_path(s3_path: str):
    # s3://bucket/key...
    if not s3_path.startswith("s3://"):
        raise ValueError(f"s3_path inválido: {s3_path}")
    no_scheme = s3_path[len("s3://"):]
    parts = no_scheme.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"s3_path inválido: {s3_path}")
    return parts[0], parts[1]

def get_latest_delete_marker(s3, bucket: str, key: str):
    """
    Retorna el delete marker más reciente (VersionId + LastModified) para ese key.
    Si no existe delete marker, retorna None.
    """
    resp = s3.list_object_versions(Bucket=bucket, Prefix=key)

    dms = [
        dm for dm in (resp.get("DeleteMarkers") or [])
        if dm.get("Key") == key
    ]
    if not dms:
        return None

    dms.sort(key=lambda x: x["LastModified"], reverse=True)
    latest = dms[0]
    return {
        "version_id": latest.get("VersionId"),
        "last_modified": latest.get("LastModified"),
        "is_latest": latest.get("IsLatest"),
    }

def restore_by_deleting_delete_marker(s3, bucket: str, key: str, delete_marker_version_id: str):
    """
    Restaurar = borrar el delete marker (por VersionId)
    """
    s3.delete_object(Bucket=bucket, Key=key, VersionId=delete_marker_version_id)

def main():
    df = pd.read_csv(INPUT_CSV)

    if "s3_path" not in df.columns:
        raise ValueError(f"El CSV {INPUT_CSV} no tiene columna 's3_path'")

    preview_rows = []
    # Cache de clients por región para eficiencia
    s3_clients = {}

    for i, row in enumerate(df.itertuples(index=False), start=1):
        s3_path = getattr(row, "s3_path")
        region = getattr(row, "region") if hasattr(row, "region") else None
        url = getattr(row, "url") if hasattr(row, "url") else None

        bucket, key = parse_s3_path(str(s3_path))

        # region viene del CSV; si no está, usa la default de tu AWS config/ENV
        if region and region not in s3_clients:
            s3_clients[region] = boto3.client("s3", region_name=region)
        s3 = s3_clients.get(region) if region else boto3.client("s3")

        try:
            latest_dm = get_latest_delete_marker(s3, bucket, key)

            if not latest_dm:
                # Ya no hay delete marker (quizá ya restaurado)
                print(f"[{i}] (skip) NO delete marker ya: {s3_path}")
                continue

            dm_vid = latest_dm["version_id"]
            dm_time = latest_dm["last_modified"]
            dm_is_latest = latest_dm["is_latest"]

            preview_rows.append({
                "s3_path": s3_path,
                "bucket": bucket,
                "key": key,
                "region": region,
                "url": url,
                "delete_marker_version_id": dm_vid,
                "delete_marker_last_modified": str(dm_time),
                "delete_marker_is_latest": dm_is_latest,
                "action": "WOULD_RESTORE" if DRY_RUN else "RESTORED"
            })

            if DRY_RUN:
                print(f"[{i}] ✅ WOULD_RESTORE -> {s3_path} | delete_marker={dm_vid} | {dm_time}")
            else:
                restore_by_deleting_delete_marker(s3, bucket, key, dm_vid)
                print(f"[{i}] ✅ RESTORED -> {s3_path} | delete_marker_deleted={dm_vid}")

        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            print(f"[{i}] ⚠️ ERROR {code} -> {s3_path}")

    out = pd.DataFrame(preview_rows)
    out.to_csv(OUTPUT_PREVIEW_CSV, index=False, encoding="utf-8")

    print("\n--- LISTO ---")
    print(f"Total {'a restaurar (preview)' if DRY_RUN else 'restaurados'}: {len(preview_rows)}")
    print(f"✅ Archivo generado: {OUTPUT_PREVIEW_CSV}")

if __name__ == "__main__":
    main()
