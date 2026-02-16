import csv
import re
import time
from urllib.parse import urlparse
import boto3
from collections import Counter

# =========================
# Config
# =========================
REGION = "us-west-2"
MAX_PAGES = 31
TAIL_BYTES = 1024 * 1024  # 1 MB

INPUT_CSV = "pinecone_results_not_found.csv"
OUTPUT_IGNORED = "pdf_ignorados_mas_20_paginas.csv"
OUTPUT_VALID = "pdf_validos_hasta_20_paginas.csv"

# Logging / progreso
VERBOSE = True
PRINT_EVERY = 50
SHOW_SPEED = True

# Stats
TOP_MODES_TO_SHOW = 5  # si hay empates o varias modas, mostrar top N

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

    # Aquí vamos a acumular SOLO los pages de ignorados por >20
    pages_ignored_gt20 = []

    # ✅ NUEVO: track del documento con más páginas (solo PAGES_GT_20)
    max_pages_record = None  # {"MIU_DOCUMENTOS":..., "PATH_ADUNTO":..., "PAGINAS_DETECTADAS":...}

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

            if pages == 0:
                record["MOTIVO"] = "PAGES_0"
                ignored.append(record)
                status = "IGNORADO"

            elif pages > MAX_PAGES:
                record["MOTIVO"] = "PAGES_GT_20"
                ignored.append(record)
                pages_ignored_gt20.append(pages)  # ✅ solo estos entran a stats
                status = "IGNORADO"

                # ✅ NUEVO: actualizar máximo de páginas detectadas (solo PAGES_GT_20)
                if (max_pages_record is None) or (pages > max_pages_record["PAGINAS_DETECTADAS"]):
                    max_pages_record = {
                        "MIU_DOCUMENTOS": miu_documentos,
                        "PATH_ADUNTO": path,
                        "PAGINAS_DETECTADAS": pages
                    }

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
    # Stats: ignorados por pages > 20 (excluye pages=0 y errores)
    # =========================
    print("\n📊 Estadísticas ( > 30)")
    if pages_ignored_gt20:
        avg_pages = sum(pages_ignored_gt20) / len(pages_ignored_gt20)

        c = Counter(pages_ignored_gt20)
        max_freq = max(c.values())
        modes = [p for p, freq in c.items() if freq == max_freq]
        modes_sorted = sorted(modes)

        print(f"→ Promedio de páginas: {avg_pages:.2f}")

        if len(modes_sorted) == 1:
            print(f"→ Moda de páginas: {modes_sorted[0]} (frecuencia={max_freq})")
        else:
            print(f"→ Modas (empate, frecuencia={max_freq}): {modes_sorted[:TOP_MODES_TO_SHOW]}"
                  + (" ..." if len(modes_sorted) > TOP_MODES_TO_SHOW else ""))
            top = c.most_common(TOP_MODES_TO_SHOW)
            print(f"→ Top {TOP_MODES_TO_SHOW} páginas más frecuentes: {top}")

        # ✅ NUEVO: máximo y documento asociado
        if max_pages_record is not None:
            print(f"→ Máximo de páginas detectadas: {max_pages_record['PAGINAS_DETECTADAS']}")
            print(f"   - MIU_DOCUMENTOS: {max_pages_record['MIU_DOCUMENTOS']}")
            print(f"   - PATH_ADUNTO: {max_pages_record['PATH_ADUNTO']}")

    # =========================
    # CSV - Ignorados
    # =========================
    with open(OUTPUT_IGNORED, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["MIU_DOCUMENTOS", "PATH_ADUNTO", "PAGINAS_DETECTADAS", "MOTIVO", "ERROR"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in ignored:
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
    print(f"→ Ignorados ( >{MAX_PAGES}): {len(ignored)}")
    print(f"→ Tiempo total: {elapsed_total:.1f}s")
    if SHOW_SPEED:
        print(f"→ Velocidad promedio: {fmt_rate(total, elapsed_total)}")
    print(f"→ CSV ignorados: {OUTPUT_IGNORED}")
    print(f"→ CSV válidos: {OUTPUT_VALID}")


if __name__ == "__main__":
    main()
