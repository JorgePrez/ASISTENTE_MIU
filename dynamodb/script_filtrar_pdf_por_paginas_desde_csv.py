import csv
import re
import time
from urllib.parse import urlparse
import boto3

# =========================
# Config
# =========================
REGION = "us-west-2"
MAX_PAGES = 20
TAIL_BYTES = 1024 * 1024  # 1 MB

INPUT_CSV = "pinecone_results_not_found.csv"
OUTPUT_IGNORED = "pdf_ignorados_mas_20_paginas.csv"
OUTPUT_VALID = "pdf_validos_hasta_20_paginas.csv"

# Logging / progreso
VERBOSE = True          # True = imprime cada archivo
PRINT_EVERY = 50        # imprime resumen cada N filas (aunque VERBOSE=False)
SHOW_SPEED = True       # muestra docs/seg

# =========================
# AWS
# =========================
s3 = boto3.client("s3", region_name=REGION)

# =========================
# Helpers
# =========================
def parse_s3_from_url(url: str):
    url = url.strip()
    if url.startswith("s3://"):
        u = urlparse(url)
        return u.netloc, u.path.lstrip("/")
    if url.startswith("http"):
        u = urlparse(url)
        bucket = u.netloc.split(".s3")[0]
        key = u.path.lstrip("/")
        return bucket, key
    raise ValueError(f"Formato S3 no soportado: {url}")


def count_pdf_pages_fast(bucket: str, key: str) -> int:
    head = s3.head_object(Bucket=bucket, Key=key)
    size = head["ContentLength"]

    start = max(0, size - TAIL_BYTES)
    byte_range = f"bytes={start}-{size - 1}"

    obj = s3.get_object(Bucket=bucket, Key=key, Range=byte_range)
    tail = obj["Body"].read()

    return len(re.findall(rb"/Type\s*/Page[^s]", tail))


def fmt_rate(done: int, elapsed: float) -> str:
    if elapsed <= 0:
        return "∞"
    return f"{done/elapsed:.2f} docs/s"


# =========================
# Main
# =========================
def main():
    ignored = []
    valid = []

    # Leer todo para saber total (progreso %)
    with open(INPUT_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    total = len(rows)
    t0 = time.time()

    print(f"→ Total filas a procesar: {total}")
    print(f"→ Límite páginas: {MAX_PAGES} (y pages=0 también se ignora)")
    print(f"→ Lectura parcial (tail): {TAIL_BYTES/1024:.0f} KB")
    print("-" * 60)

    for i, row in enumerate(rows, start=1):
        miu_documentos = row.get("MIU_DOCUMENTOS", "").strip()
        path = (row.get("PATH_ADUNTO") or "").strip()

        try:
            bucket, key = parse_s3_from_url(path)
            pages = count_pdf_pages_fast(bucket, key)

            record = {
                "MIU_DOCUMENTOS": miu_documentos,
                "PATH_ADUNTO": path,
                "PAGINAS_DETECTADAS": pages
            }

            # ✅ Nueva regla:
            # - pages == 0 => ignorar (asumimos PDF enorme / no contable por método rápido)
            # - pages > MAX_PAGES => ignorar
            if pages == 0:
                record["MOTIVO"] = "PAGES_0"
                ignored.append(record)
                status = "IGNORADO"
            elif pages > MAX_PAGES:
                record["MOTIVO"] = "PAGES_GT_20"
                ignored.append(record)
                status = "IGNORADO"
            else:
                valid.append(record)
                status = "OK"

            if VERBOSE:
                motivo = record.get("MOTIVO", "")
                motivo_str = f" | motivo={motivo}" if motivo else ""
                print(f"[{i}/{total}] {status:8} | MIU={miu_documentos} | pages={pages}{motivo_str} | {path}")

        except Exception as e:
            ignored.append({
                "MIU_DOCUMENTOS": miu_documentos,
                "PATH_ADUNTO": path,
                "PAGINAS_DETECTADAS": "ERROR",
                "MOTIVO": "ERROR",
                "ERROR": str(e)
            })
            if VERBOSE:
                print(f"[{i}/{total}] ERROR    | MIU={miu_documentos} | {path} | {e}")

        # Progreso cada N filas (aunque VERBOSE=False)
        if (i % PRINT_EVERY == 0) or (i == total):
            elapsed = time.time() - t0
            pct = (i / total) * 100 if total else 100
            rate = fmt_rate(i, elapsed) if SHOW_SPEED else ""
            print("-" * 60)
            print(
                f"Progreso: {i}/{total} ({pct:.1f}%) | "
                f"OK={len(valid)} | Ignorados/Errores={len(ignored)}"
                + (f" | {rate}" if rate else "")
            )
            print("-" * 60)

    # =========================
    # CSV - Ignorados
    # =========================
    with open(OUTPUT_IGNORED, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["MIU_DOCUMENTOS", "PATH_ADUNTO", "PAGINAS_DETECTADAS", "MOTIVO", "ERROR"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in ignored:
            # asegurar llaves para CSV
            if "MOTIVO" not in r:
                r["MOTIVO"] = ""
            if "ERROR" not in r:
                r["ERROR"] = ""
            writer.writerow(r)

    # =========================
    # CSV - Válidos
    # =========================
    with open(OUTPUT_VALID, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["MIU_DOCUMENTOS", "PATH_ADUNTO", "PAGINAS_DETECTADAS"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in valid:
            writer.writerow(r)

    elapsed_total = time.time() - t0
    print("\n✔ Terminado")
    print(f"→ Válidos (1..{MAX_PAGES} páginas): {len(valid)}")
    print(f"→ Ignorados/Errores (pages=0, >{MAX_PAGES} o error): {len(ignored)}")
    print(f"→ Tiempo total: {elapsed_total:.1f}s")
    if SHOW_SPEED:
        print(f"→ Velocidad promedio: {fmt_rate(total, elapsed_total)}")
    print(f"→ CSV ignorados: {OUTPUT_IGNORED}")
    print(f"→ CSV válidos: {OUTPUT_VALID}")


if __name__ == "__main__":
    main()
