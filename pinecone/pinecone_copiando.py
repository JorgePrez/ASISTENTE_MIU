import os
import json
import time
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =========================================================
# CONFIGURACION
# =========================================================
API_KEY = 'pcsk_i8GnP_JEpQMBkWnne9ggLiygRHZnx871pCmKgWpZCjh46oH8JhGvPToUoMAN6KTvp9NkL'

SOURCE_INDEX_HOST = "miu-documentos-vz16bim.svc.apw5-4e34-81fa.pinecone.io"
##TARGET_INDEX_HOST = "prueba-miu-documentos-vz16bim.svc.aped-4627-b74a.pinecone.io"
TARGET_INDEX_HOST = "miu-documentos-east-vz16bim.svc.aped-4627-b74a.pinecone.io"


# IMPORTANTE: si el namespace tiene espacio final, dejalo exactamente asi
SOURCE_NAMESPACE = "namespace "
TARGET_NAMESPACE = "namespace "

FIELD_NAME = "x-amz-bedrock-kb-data-source-id"
FIELD_VALUE = "SN6AHHD0JV"

# Pinecone en tu caso practico te esta devolviendo 100
FETCH_LIMIT = 100

# Upsert por lotes dentro de cada pagina
UPSERT_BATCH_SIZE = 100

# Workers para hacer upsert en paralelo
MAX_UPSERT_WORKERS = 8

# API version
API_VERSION_FETCH = "2025-10"
API_VERSION_UPSERT = "2025-04"

# Guardar progreso
SAVE_PROGRESS = True
PROGRESS_FILE = "pinecone_migration_progress.json"
MIGRATED_IDS_FILE = "migrated_ids.jsonl"

# Si solo vas a migrar vectores raw, values debe ir en True
INCLUDE_VALUES = True
INCLUDE_METADATA = True

REQUEST_TIMEOUT = 120

# =========================================================
# VALIDACION
# =========================================================
if not API_KEY:
    raise ValueError(
        "No se encontro PINECONE_API_KEY. "
        "En PowerShell usa: $env:PINECONE_API_KEY='TU_API_KEY'"
    )

# =========================================================
# URLS
# =========================================================
SOURCE_FETCH_URL = f"https://{SOURCE_INDEX_HOST}/vectors/fetch_by_metadata"
TARGET_UPSERT_URL = f"https://{TARGET_INDEX_HOST}/vectors/upsert"

FETCH_HEADERS = {
    "Api-Key": API_KEY,
    "Content-Type": "application/json",
    "X-Pinecone-API-Version": API_VERSION_FETCH
}

UPSERT_HEADERS = {
    "Api-Key": API_KEY,
    "Content-Type": "application/json",
    "X-Pinecone-API-Version": API_VERSION_UPSERT
}

FILTER = {
    FIELD_NAME: {
        "$eq": FIELD_VALUE
    }
}

# =========================================================
# ESTADO GLOBAL
# =========================================================
lock = threading.Lock()
stats = {
    "pages_read": 0,
    "records_found": 0,
    "records_upserted": 0,
    "upsert_batches_ok": 0,
    "upsert_batches_failed": 0,
    "start_time": None
}


# =========================================================
# HELPERS
# =========================================================
def build_session(pool_size=20):
    session = requests.Session()

    retry_strategy = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=1.2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"]
    )

    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=pool_size,
        pool_maxsize=pool_size
    )

    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def normalize_records(data):
    records = data.get("vectors") or data.get("records") or []

    if isinstance(records, dict):
        normalized = []
        for rid, rdata in records.items():
            item = {"id": rid}
            if isinstance(rdata, dict):
                item.update(rdata)
            normalized.append(item)
        return normalized

    if isinstance(records, list):
        return records

    return []


def chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def append_jsonl_ids(records, file_path):
    with open(file_path, "a", encoding="utf-8") as f:
        for record in records:
            rid = record.get("id")
            if rid:
                f.write(json.dumps({"id": rid}, ensure_ascii=False) + "\n")


def save_progress_file():
    if not SAVE_PROGRESS:
        return
    payload = {
        "source_index_host": SOURCE_INDEX_HOST,
        "target_index_host": TARGET_INDEX_HOST,
        "source_namespace": SOURCE_NAMESPACE,
        "target_namespace": TARGET_NAMESPACE,
        "filter": FILTER,
        "stats": stats,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


# =========================================================
# FETCH SOURCE PAGE
# =========================================================
def fetch_page(source_session, pagination_token=None):
    body = {
        "namespace": SOURCE_NAMESPACE,
        "filter": FILTER,
        "limit": FETCH_LIMIT,
        "includeMetadata": INCLUDE_METADATA,
        "includeValues": INCLUDE_VALUES
    }

    if pagination_token:
        body["paginationToken"] = pagination_token

    response = source_session.post(
        SOURCE_FETCH_URL,
        headers=FETCH_HEADERS,
        json=body,
        timeout=REQUEST_TIMEOUT
    )

    if response.status_code != 200:
        raise Exception(
            f"[FETCH ERROR] HTTP {response.status_code}\n"
            f"Response: {response.text}"
        )

    return response.json()


# =========================================================
# UPSERT TARGET
# =========================================================
def build_upsert_vectors(records):
    vectors = []
    for record in records:
        rid = record.get("id")
        values = record.get("values")
        metadata = record.get("metadata", {})

        if not rid:
            continue
        if values is None:
            continue

        vectors.append({
            "id": rid,
            "values": values,
            "metadata": metadata
        })
    return vectors


def upsert_batch(target_session, batch_records, page_num, batch_num):
    vectors = build_upsert_vectors(batch_records)
    if not vectors:
        return {
            "ok": True,
            "count": 0,
            "page_num": page_num,
            "batch_num": batch_num
        }

    body = {
        "namespace": TARGET_NAMESPACE,
        "vectors": vectors
    }

    response = target_session.post(
        TARGET_UPSERT_URL,
        headers=UPSERT_HEADERS,
        json=body,
        timeout=REQUEST_TIMEOUT
    )

    if response.status_code != 200:
        return {
            "ok": False,
            "count": 0,
            "page_num": page_num,
            "batch_num": batch_num,
            "error": f"HTTP {response.status_code} | {response.text}"
        }

    return {
        "ok": True,
        "count": len(vectors),
        "page_num": page_num,
        "batch_num": batch_num
    }


# =========================================================
# MAIN
# =========================================================
def main():
    stats["start_time"] = time.time()

    source_session = build_session(pool_size=10)
    target_session = build_session(pool_size=max(10, MAX_UPSERT_WORKERS * 2))

    pagination_token = None
    page_num = 0

    if os.path.exists(MIGRATED_IDS_FILE):
        os.remove(MIGRATED_IDS_FILE)

    print("====================================================")
    print("MIGRACION DIRECTA PINECONE")
    print("====================================================")
    print(f"Origen   : {SOURCE_INDEX_HOST}")
    print(f"Destino  : {TARGET_INDEX_HOST}")
    print(f"NS src   : '{SOURCE_NAMESPACE}'")
    print(f"NS dst   : '{TARGET_NAMESPACE}'")
    print(f"Filtro   : {FIELD_NAME} == {FIELD_VALUE}")
    print(f"Fetch    : {FETCH_LIMIT} por pagina")
    print(f"Upsert   : {UPSERT_BATCH_SIZE} por lote")
    print(f"Workers  : {MAX_UPSERT_WORKERS}")
    print("====================================================\n")

    with ThreadPoolExecutor(max_workers=MAX_UPSERT_WORKERS) as executor:
        while True:
            page_num += 1
            page_start = time.time()

            data = fetch_page(source_session, pagination_token)
            records = normalize_records(data)
            batch_count = len(records)

            with lock:
                stats["pages_read"] += 1
                stats["records_found"] += batch_count

            if batch_count == 0:
                print(f"[PAGE {page_num}] 0 registros. Fin.")
                break

            print(
                f"[PAGE {page_num}] leidos={batch_count} | "
                f"encontrados_acum={stats['records_found']}"
            )

            append_jsonl_ids(records, MIGRATED_IDS_FILE)

            futures = []
            for batch_num, sub_batch in enumerate(chunked(records, UPSERT_BATCH_SIZE), start=1):
                futures.append(
                    executor.submit(upsert_batch, target_session, sub_batch, page_num, batch_num)
                )

            page_upserted = 0
            for future in as_completed(futures):
                result = future.result()

                if result["ok"]:
                    page_upserted += result["count"]
                    with lock:
                        stats["records_upserted"] += result["count"]
                        stats["upsert_batches_ok"] += 1

                    print(
                        f"   [UPSERT OK] page={result['page_num']} "
                        f"batch={result['batch_num']} "
                        f"count={result['count']} | "
                        f"upserted_acum={stats['records_upserted']}"
                    )
                else:
                    with lock:
                        stats["upsert_batches_failed"] += 1

                    print(
                        f"   [UPSERT FAIL] page={result['page_num']} "
                        f"batch={result['batch_num']} | "
                        f"{result['error']}"
                    )

            pagination = data.get("pagination", {}) or {}
            pagination_token = (
                pagination.get("next")
                or pagination.get("next_token")
                or data.get("paginationToken")
            )

            elapsed_page = time.time() - page_start
            elapsed_total = time.time() - stats["start_time"]

            print(
                f"[PAGE {page_num} DONE] "
                f"upserted_page={page_upserted} | "
                f"tiempo_pagina={elapsed_page:.2f}s | "
                f"tiempo_total={elapsed_total:.2f}s\n"
            )

            save_progress_file()

            if not pagination_token:
                break

    total_elapsed = time.time() - stats["start_time"]

    print("====================================================")
    print("RESULTADO FINAL")
    print("====================================================")
    print(f"Paginas leidas        : {stats['pages_read']}")
    print(f"Registros encontrados : {stats['records_found']}")
    print(f"Registros upserted    : {stats['records_upserted']}")
    print(f"Lotes OK              : {stats['upsert_batches_ok']}")
    print(f"Lotes FAIL            : {stats['upsert_batches_failed']}")
    print(f"Tiempo total          : {total_elapsed:.2f}s")
    print(f"IDs migrados          : {MIGRATED_IDS_FILE}")
    if SAVE_PROGRESS:
        print(f"Progreso              : {PROGRESS_FILE}")
    print("====================================================")


if __name__ == "__main__":
    main()