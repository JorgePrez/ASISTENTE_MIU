import requests
import json
import time

# =========================================================
# CONFIGURACION
# =========================================================
API_KEY = 'pcsk_i8GnP_JEpQMBkWnne9ggLiygRHZnx871pCmKgWpZCjh46oH8JhGvPToUoMAN6KTvp9NkL'
INDEX_HOST = "miu-documentos-vz16bim.svc.apw5-4e34-81fa.pinecone.io"

# IMPORTANTE: tu namespace s� lleva espacio final
NAMESPACE = "namespace "

FIELD_NAME = "x-amz-bedrock-kb-data-source-id"
FIELD_VALUE = "GERVMMQQKG"

# Cu�ntos traer por p�gina
LIMIT = 100

# Guardar resultados
SAVE_RESULTS = True
OUTPUT_FILE = "pinecone_fetch_by_metadata_result.json"

# Si quieres traer values, cambia a True
INCLUDE_VALUES = False
INCLUDE_METADATA = True

# =========================================================
# HEADERS Y URL
# =========================================================
BASE_URL = f"https://{INDEX_HOST}"
URL = f"{BASE_URL}/vectors/fetch_by_metadata"

HEADERS = {
    "Api-Key": API_KEY,
    "Content-Type": "application/json",
    # usa una versi�n moderna del endpoint
    "X-Pinecone-API-Version": "2025-10"
}

FILTER = {
    FIELD_NAME: {
        "$eq": FIELD_VALUE
    }
}


def fetch_page(pagination_token=None):
    body = {
        "namespace": NAMESPACE,
        "filter": FILTER,
        "limit": LIMIT,
        "includeMetadata": INCLUDE_METADATA,
        "includeValues": INCLUDE_VALUES
    }

    if pagination_token:
        body["paginationToken"] = pagination_token

    response = requests.post(URL, headers=HEADERS, json=body, timeout=120)

    if response.status_code != 200:
        raise Exception(
            f"HTTP {response.status_code}\n"
            f"Response: {response.text}"
        )

    return response.json()


def main():
    total_matches = 0
    page_num = 0
    pagination_token = None

    all_ids = []
    all_records = []

    start_time = time.time()

    print("==============================================")
    print("FETCH BY METADATA - PINECONE")
    print("==============================================")
    print(f"Host       : {INDEX_HOST}")
    print(f"Namespace  : '{NAMESPACE}'")
    print(f"Filtro     : {FIELD_NAME} == {FIELD_VALUE}")
    print(f"Limit/page : {LIMIT}")
    print("==============================================\n")

    while True:
        page_num += 1
        data = fetch_page(pagination_token)

        # Dependiendo de la respuesta, Pinecone devuelve los vectores/records
        records = data.get("vectors") or data.get("records") or []

        # Si vinieran como dict {id: {...}}, los convertimos a lista uniforme
        if isinstance(records, dict):
            normalized = []
            for rid, rdata in records.items():
                item = {"id": rid}
                if isinstance(rdata, dict):
                    item.update(rdata)
                normalized.append(item)
            records = normalized

        batch_count = len(records)
        total_matches += batch_count

        print(f"[PAGE {page_num}] registros={batch_count} | acumulado={total_matches}")

        for record in records:
            rid = record.get("id")
            if rid is not None:
                all_ids.append(rid)
                all_records.append(record)

        pagination = data.get("pagination", {}) or {}
        pagination_token = pagination.get("next") or pagination.get("next_token") or data.get("paginationToken")

        if not pagination_token or batch_count == 0:
            break

    elapsed = time.time() - start_time

    print("\n==============================================")
    print("RESULTADO FINAL")
    print("==============================================")
    print(f"Total vectores encontrados: {total_matches}")
    print(f"Tiempo total              : {elapsed:.2f}s")
    print("==============================================")

    if SAVE_RESULTS:
        output = {
            "index_host": INDEX_HOST,
            "namespace": NAMESPACE,
            "filter": FILTER,
            "limit": LIMIT,
            "total_matches": total_matches,
            "ids": all_ids,
            "records": all_records if INCLUDE_METADATA or INCLUDE_VALUES else []
        }

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f"Archivo generado: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()