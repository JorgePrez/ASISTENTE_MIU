from pinecone import Pinecone
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

PINECONE_API_KEY = 'pcsk_i8GnP_JEpQMBkWnne9ggLiygRHZnx871pCmKgWpZCjh46oH8JhGvPToUoMAN6KTvp9NkL'
INDEX_HOST = "miu-documentos-vz16bim.svc.apw5-4e34-81fa.pinecone.io"
NAMESPACE = "namespace "

FIELD_NAME = "x-amz-bedrock-kb-data-source-id"
TARGET_VALUE = "GERVMMQQKG"

MAX_WORKERS = 20
LIST_LIMIT = 100   # Pinecone list permite limit; 100 es el default

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(host=INDEX_HOST)


def process_batch(batch_num, ids_batch):
    t0 = time.time()
    response = index.fetch(ids=ids_batch, namespace=NAMESPACE)
    vectors = response.get("vectors", {})

    count = 0
    for vid, data in vectors.items():
        metadata = data.get("metadata", {}) or {}
        if metadata.get(FIELD_NAME) == TARGET_VALUE:
            count += 1

    elapsed = time.time() - t0
    return {
        "batch_num": batch_num,
        "ids_count": len(ids_batch),
        "match_count": count,
        "elapsed": elapsed,
    }


def fast_count():
    total_ids = 0
    total_matches = 0
    submitted = 0
    completed = 0
    futures = []

    t0 = time.time()

    print("Iniciando listado y envio de batches...\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # OJO: aqu� s� pedimos m�s de 100 por p�gina
        for batch_num, ids_batch in enumerate(index.list(namespace=NAMESPACE, limit=LIST_LIMIT), start=1):
            ids_batch = list(ids_batch)
            if not ids_batch:
                continue

            submitted += 1
            total_ids += len(ids_batch)

            print(f"[ENVIADO {batch_num}] ids={len(ids_batch)} | total_ids_vistos={total_ids}")

            future = executor.submit(process_batch, batch_num, ids_batch)
            futures.append(future)

        print(f"\nTodos los batches fueron enviados. Total batches: {submitted}\n")

        for future in as_completed(futures):
            result = future.result()
            completed += 1
            total_matches += result["match_count"]

            print(
                f"[COMPLETADO {result['batch_num']}] "
                f"ids={result['ids_count']} | "
                f"matches_batch={result['match_count']} | "
                f"matches_acumulados={total_matches} | "
                f"duracion={result['elapsed']:.2f}s | "
                f"completados={completed}/{submitted}"
            )

    total_elapsed = time.time() - t0

    print("\n================ RESULTADO FINAL ================")
    print(f"Total IDs recorridos : {total_ids}")
    print(f"Total matches        : {total_matches}")
    print(f"Tiempo total         : {total_elapsed:.2f}s")
    print("================================================")


if __name__ == "__main__":
    fast_count()