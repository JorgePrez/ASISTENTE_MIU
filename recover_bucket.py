#!/usr/bin/env python3
"""
restore_s3_delete_markers_safe.py

Restaura objetos que actualmente están borrados (latest = delete marker).
No toca objetos que actualmente existen (latest != delete marker).

Uso:
  python restore_s3_delete_markers_safe.py --bucket mi-bucket --region us-east-1
  python restore_s3_delete_markers_safe.py --bucket mi-bucket --region us-east-1 --execute
"""

import argparse
import boto3
from collections import defaultdict
from datetime import datetime, timezone
import sys

def parse_args():
    p = argparse.ArgumentParser(description="Restaurar objetos borrados en un bucket S3 (solo claves cuyo latest es delete marker).")
    p.add_argument("--bucket", required=True, help="Nombre del bucket S3")
    p.add_argument("--region", required=True, help="Región AWS (ej: us-east-1)")
    p.add_argument("--profile", required=False, default=None, help="Perfil AWS (opcional)")
    p.add_argument("--execute", action="store_true", help="Ejecuta las eliminaciones (por defecto dry-run).")
    p.add_argument("--prefix", required=False, default=None, help="Prefijo para limitar a objetos bajo este prefijo (opcional).")
    return p.parse_args()

def make_client(region, profile=None):
    session_kwargs = {}
    if profile:
        session_kwargs["profile_name"] = profile
    if session_kwargs:
        session = boto3.Session(**session_kwargs)
    else:
        session = boto3.Session()
    return session.client("s3", region_name=region)

def collect_versions(client, bucket, prefix=None):
    """
    Devuelve dict:
    { key: [ { 'IsDeleteMarker': bool, 'VersionId': str, 'LastModified': datetime, 'IsLatest': bool }, ... ] }
    """
    paginator = client.get_paginator("list_object_versions")
    pagination_args = {"Bucket": bucket}
    if prefix:
        pagination_args["Prefix"] = prefix

    by_key = defaultdict(list)
    for page in paginator.paginate(**pagination_args):
        # Versions
        for v in page.get("Versions", []):
            by_key[v["Key"]].append({
                "IsDeleteMarker": False,
                "VersionId": v["VersionId"],
                "LastModified": v["LastModified"] if isinstance(v["LastModified"], datetime) else datetime.strptime(v["LastModified"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc),
                "IsLatest": bool(v.get("IsLatest", False))
            })
        # DeleteMarkers
        for dm in page.get("DeleteMarkers", []):
            by_key[dm["Key"]].append({
                "IsDeleteMarker": True,
                "VersionId": dm["VersionId"],
                "LastModified": dm["LastModified"] if isinstance(dm["LastModified"], datetime) else datetime.strptime(dm["LastModified"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc),
                "IsLatest": bool(dm.get("IsLatest", False))
            })
    return by_key

def plan_and_execute(client, bucket, by_key, execute=False):
    total_keys = 0
    candidates = 0
    restored_keys = 0
    skipped_existing = 0
    skipped_no_non_delete = 0

    for key, items in by_key.items():
        total_keys += 1

        # Determine if the current latest is a delete marker.
        latest_items = [it for it in items if it.get("IsLatest", False)]
        # There should normally be exactly one IsLatest==True, but be robust:
        latest_is_delete = any(it["IsDeleteMarker"] for it in latest_items)

        if not latest_is_delete:
            # Objeto actualmente existe -> saltar
            skipped_existing += 1
            # Optional: verbose
            print(f"[SKIP_EXISTING] {key}: El objeto actualmente existe (latest no es delete marker). No se restaurará.")
            continue

        # Ahora procesamos solo claves cuyo latest es delete marker
        candidates += 1

        # sort by LastModified desc (más reciente primero)
        items_sorted = sorted(items, key=lambda x: x["LastModified"], reverse=True)

        # Encuentra la versión no-delete más reciente
        most_recent_non_delete = None
        for it in items_sorted:
            if not it["IsDeleteMarker"]:
                most_recent_non_delete = it
                break

        if not most_recent_non_delete:
            print(f"[SKIP_NO_NONDELETE] {key}: Solo hay delete markers (no hay versión no-delete). No se puede restaurar.")
            skipped_no_non_delete += 1
            continue

        # Delete markers que sean iguales o posteriores a esa versión (ocultando la versión)
        dm_to_remove = [it for it in items_sorted if it["IsDeleteMarker"] and it["LastModified"] >= most_recent_non_delete["LastModified"]]

        if not dm_to_remove:
            print(f"[OK] {key}: La versión {most_recent_non_delete['VersionId']} ya sería visible (no hay delete markers que la oculten).")
            continue

        print(f"[PLAN] {key}: Restaurar VersionId={most_recent_non_delete['VersionId']} eliminando {len(dm_to_remove)} delete marker(s): {[d['VersionId'] for d in dm_to_remove]}")
        if execute:
            for d in dm_to_remove:
                try:
                    client.delete_object(Bucket=bucket, Key=key, VersionId=d["VersionId"])
                    print(f"  -> Eliminado delete marker VersionId={d['VersionId']}")
                except Exception as e:
                    print(f"  !! Error eliminando delete marker {d['VersionId']} en {key}: {e}", file=sys.stderr)
            restored_keys += 1
        else:
            print("  (dry-run; usa --execute para aplicar cambios)")

    print("\nResumen:")
    print(f"  claves inspeccionadas: {total_keys}")
    print(f"  claves candidatas (latest = delete marker): {candidates}")
    print(f"  claves saltadas (actualmente existen): {skipped_existing}")
    print(f"  claves saltadas (solo delete markers, sin versiones previas): {skipped_no_non_delete}")
    print(f"  claves restauradas (ejecutadas): {restored_keys if execute else '0 (dry-run)'}")

def main():
    args = parse_args()
    client = make_client(args.region, profile=args.profile)

    print(f"Reuniendo versiones y delete markers en bucket '{args.bucket}' (region={args.region}) ...")
    by_key = collect_versions(client, args.bucket, prefix=args.prefix)
    if not by_key:
        print("No se encontraron versiones ni delete markers en el bucket (o no tienes permisos / bucket vacío).")
        return

    print(f"Encontradas {len(by_key)} claves con versiones/delete markers. Analizando...")
    plan_and_execute(client, args.bucket, by_key, execute=args.execute)

if __name__ == "__main__":
    main()
