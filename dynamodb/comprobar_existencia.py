#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
comprobar_existencia.py

Lee un CSV con columnas:
  - miu_documentos
  - path_adunto

y separa en 2 archivos:
  - existentes.csv
  - no_existentes.csv

Asume AWS configurado. Bucket: miu-documentos. Región: us-west-2.

Uso:
  python comprobar_existencia.py --input documentos.csv
  python comprobar_existencia.py --input documentos.csv --out-exist existentes.csv --out-no no_existentes.csv
"""

import argparse
import csv
import re
from urllib.parse import urlparse, unquote

import boto3
from botocore.exceptions import ClientError


BUCKET = "miu-documentos"
REGION = "us-west-2"


def key_from_path(path_adunto: str) -> str | None:
    """
    Extrae el S3 key desde:
      - s3://miu-documentos/KEY
      - https://miu-documentos.s3.us-west-2.amazonaws.com/KEY
      - https://s3.us-west-2.amazonaws.com/miu-documentos/KEY
      - o si viene KEY directo: DATA-DOCS/...
    """
    if not path_adunto:
        return None

    raw = path_adunto.strip().strip('"').strip("'")
    if not raw:
        return None

    # s3://...
    if raw.lower().startswith("s3://"):
        u = urlparse(raw)
        if u.netloc and u.netloc != BUCKET:
            # Si algún día cambia, aquí lo ignoramos a propósito: siempre usamos BUCKET fijo
            pass
        return unquote(u.path.lstrip("/")) or None

    # http(s)://...
    if raw.lower().startswith("http://") or raw.lower().startswith("https://"):
        u = urlparse(raw)
        host = (u.netloc or "").lower()
        path = unquote(u.path.lstrip("/"))

        # miu-documentos.s3.<region>.amazonaws.com/KEY  o  miu-documentos.s3.amazonaws.com/KEY
        if host.startswith(f"{BUCKET}.s3.") or host == f"{BUCKET}.s3.amazonaws.com":
            return path or None

        # s3.<region>.amazonaws.com/miu-documentos/KEY  o  s3.amazonaws.com/miu-documentos/KEY
        if host.startswith("s3.") or host == "s3.amazonaws.com":
            if path.startswith(BUCKET + "/"):
                return path[len(BUCKET) + 1 :] or None

        # Si es otro dominio, no adivinamos
        return None

    # key directo
    return raw.lstrip("/") or None


def exists_in_s3(s3_client, key: str) -> tuple[bool, str]:
    """
    Retorna (existe, motivo_si_no)
    """
    try:
        s3_client.head_object(Bucket=BUCKET, Key=key)
        return True, ""
    except ClientError as e:
        status = int(e.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0) or 0)
        code = e.response.get("Error", {}).get("Code", "")

        if status == 404 or code in ("NoSuchKey", "NotFound", "404"):
            return False, "NoSuchKey/404"
        if status == 403 or code in ("AccessDenied", "403"):
            # OJO: esto puede significar "existe pero no tengo permisos"
            return False, "AccessDenied/403"
        return False, f"{code or 'ClientError'} ({status})"
    except Exception as e:
        return False, repr(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", "-i", required=True, help="CSV de entrada")
    ap.add_argument("--out-exist", default="existentes.csv", help="Salida: existentes")
    ap.add_argument("--out-no", default="no_existentes.csv", help="Salida: no existentes")
    args = ap.parse_args()

    s3 = boto3.client("s3", region_name=REGION)

    with open(args.input, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        lower = {c.lower(): c for c in fieldnames}

        col_id = lower.get("miu_documentos")
        col_path = lower.get("path_adunto")

        if not col_id or not col_path:
            raise SystemExit(
                f"No encontré columnas requeridas. Encabezados: {fieldnames}. "
                f"Se esperan: miu_documentos y path_adunto"
            )

        rows = list(reader)

    # Agregamos columnas útiles (pero seguimos escribiendo 2 CSVs)
    out_fields = list(fieldnames)
    for extra in ["s3_key", "motivo"]:
        if extra not in out_fields:
            out_fields.append(extra)

    with open(args.out_exist, "w", encoding="utf-8", newline="") as f_ok, open(
        args.out_no, "w", encoding="utf-8", newline=""
    ) as f_no:
        w_ok = csv.DictWriter(f_ok, fieldnames=out_fields)
        w_no = csv.DictWriter(f_no, fieldnames=out_fields)
        w_ok.writeheader()
        w_no.writeheader()

        for r in rows:
            path = str(r.get(col_path, "")).strip()
            key = key_from_path(path)

            if not key:
                r["s3_key"] = ""
                r["motivo"] = "No se pudo parsear key desde path_adunto"
                w_no.writerow(r)
                continue

            ok, motivo = exists_in_s3(s3, key)
            r["s3_key"] = key
            r["motivo"] = motivo

            if ok:
                w_ok.writerow(r)
            else:
                w_no.writerow(r)

    print(f"Listo. Generados:\n- {args.out_exist}\n- {args.out_no}")


if __name__ == "__main__":
    main()
