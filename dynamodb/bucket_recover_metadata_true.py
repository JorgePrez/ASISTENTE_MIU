import boto3
import pandas as pd
from botocore.exceptions import ClientError

INPUT_CSV = "metadata_targets.csv"
OUTPUT_CSV = "metadata_restore_results.csv"

DRY_RUN = False  # True = solo preview, False = RESTAURA (borra delete marker)

def get_s3_client(region: str):
    return boto3.client("s3", region_name=region)

def get_latest_delete_marker(s3, bucket: str, key: str):
    """
    Retorna dict con VersionId/LastModified del delete marker más reciente para ese key.
    Si no hay delete marker, retorna None.
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

def delete_delete_marker(s3, bucket: str, key: str, version_id: str):
    # Restaurar = borrar delete marker específico por VersionId
    s3.delete_object(Bucket=bucket, Key=key, VersionId=version_id)

def main():
    df = pd.read_csv(INPUT_CSV)

    required = {"bucket", "region", "metadata_key"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Faltan columnas en {INPUT_CSV}: {missing}")

    s3_clients = {}
    results = []

    for i, row in enumerate(df.itertuples(index=False), start=1):
        bucket = getattr(row, "bucket")
        region = getattr(row, "region")
        key = getattr(row, "metadata_key")

        if region not in s3_clients:
            s3_clients[region] = get_s3_client(region)
        s3 = s3_clients[region]

        try:
            dm = get_latest_delete_marker(s3, bucket, key)

            if not dm:
                print(f"[{i}] (skip) NO delete marker -> s3://{bucket}/{key}")
                results.append({
                    "bucket": bucket,
                    "region": region,
                    "key": key,
                    "status": "NO_DELETE_MARKER",
                    "delete_marker_version_id": None,
                    "delete_marker_last_modified": None,
                    "action": "SKIPPED",
                })
                continue

            vid = dm["version_id"]
            ts = dm["last_modified"]

            if DRY_RUN:
                print(f"[{i}] ✅ WOULD_RESTORE -> s3://{bucket}/{key} | delete_marker={vid} | {ts}")
                results.append({
                    "bucket": bucket,
                    "region": region,
                    "key": key,
                    "status": "DELETE_MARKED",
                    "delete_marker_version_id": vid,
                    "delete_marker_last_modified": str(ts),
                    "action": "WOULD_RESTORE",
                })
            else:
                delete_delete_marker(s3, bucket, key, vid)
                print(f"[{i}] ✅ RESTORED -> s3://{bucket}/{key} | delete_marker_deleted={vid}")
                results.append({
                    "bucket": bucket,
                    "region": region,
                    "key": key,
                    "status": "DELETE_MARKED",
                    "delete_marker_version_id": vid,
                    "delete_marker_last_modified": str(ts),
                    "action": "RESTORED",
                })

        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            print(f"[{i}] ⚠️ ERROR {code} -> s3://{bucket}/{key}")
            results.append({
                "bucket": bucket,
                "region": region,
                "key": key,
                "status": f"ERROR_{code}",
                "delete_marker_version_id": None,
                "delete_marker_last_modified": None,
                "action": "FAILED",
            })

    out = pd.DataFrame(results)
    out.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")

    print("\n--- RESUMEN ---")
    print(out["action"].value_counts(dropna=False))
    print(f"✅ Archivo generado: {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
