from pinecone import Pinecone
from concurrent.futures import ThreadPoolExecutor, as_completed

PINECONE_API_KEY = 'pcsk_i8GnP_JEpQMBkWnne9ggLiygRHZnx871pCmKgWpZCjh46oH8JhGvPToUoMAN6KTvp9NkL'
INDEX_HOST = "miu-documentos-vz16bim.svc.apw5-4e34-81fa.pinecone.io"
NAMESPACE = "namespace "

FIELD_NAME = "x-amz-bedrock-kb-data-source-id"
TARGET_VALUE = "GERVMMQQKG"

MAX_WORKERS = 20  # ?? puedes subir a 20 si quieres


pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(host=INDEX_HOST)


def process_batch(ids_batch):
    response = index.fetch(ids=ids_batch, namespace=NAMESPACE)
    vectors = response.get("vectors", {})

    count = 0

    for vid, data in vectors.items():
        metadata = data.get("metadata", {}) or {}

        if metadata.get(FIELD_NAME) == TARGET_VALUE:
            count += 1

    return count


def fast_count():
    total = 0
    matched = 0

    futures = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for ids_batch in index.list(namespace=NAMESPACE):
            ids_batch = list(ids_batch)

            total += len(ids_batch)

            futures.append(executor.submit(process_batch, ids_batch))

        for future in as_completed(futures):
            result = future.result()
            matched += result
            print(f"Matches acumulados: {matched}")

    print("\nRESULTADO FINAL")
    print(f"Total: {total}")
    print(f"Matched: {matched}")


if __name__ == "__main__":
    fast_count()