from pinecone import Pinecone
import json
import time

# =========================================================
# CONFIGURACION
# =========================================================
PINECONE_API_KEY = 'pcsk_i8GnP_JEpQMBkWnne9ggLiygRHZnx871pCmKgWpZCjh46oH8JhGvPToUoMAN6KTvp9NkL'

# USA EL HOST DIRECTO, SIN https://
INDEX_HOST = "miu-documentos-vz16bim.svc.apw5-4e34-81fa.pinecone.io"

# IMPORTANTE: este namespace SI lleva espacio final
NAMESPACE = "namespace "

FIELD_NAME = "x-amz-bedrock-kb-data-source-id"
TARGET_VALUE = "GERVMMQQKG"

SAVE_MATCHED_IDS = True
OUTPUT_FILE = "vectores_filtrados.json"
PRINT_FIRST_N_MATCHES = 10


# =========================================================
# INICIALIZACION
# =========================================================
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(host=INDEX_HOST)


# =========================================================
# FUNCION PRINCIPAL
# =========================================================
def count_and_list_vectors():
    total_vectors = 0
    matched_vectors = 0
    matched_ids = []
    examples_printed = 0
    batch_number = 0

    print("=====================================================")
    print("INICIANDO RECORRIDO DEL INDICE")
    print("=====================================================")
    print(f"Host       : {INDEX_HOST}")
    print(f"Namespace  : '{NAMESPACE}'")
    print(f"Field name : {FIELD_NAME}")
    print(f"Target     : {TARGET_VALUE}")
    print("=====================================================\n")

    start_time = time.time()

    try:
        for ids_batch in index.list(namespace=NAMESPACE):
            batch_number += 1
            ids_batch = list(ids_batch)

            if not ids_batch:
                continue

            print(f"[Batch {batch_number}] IDs recibidos: {len(ids_batch)}")
            total_vectors += len(ids_batch)

            response = index.fetch(ids=ids_batch, namespace=NAMESPACE)
            vectors = response.get("vectors", {})

            batch_matches = 0

            for vector_id, vector_data in vectors.items():
                metadata = vector_data.get("metadata", {}) or {}

                if metadata.get(FIELD_NAME) == TARGET_VALUE:
                    matched_vectors += 1
                    batch_matches += 1
                    matched_ids.append(vector_id)

                    if examples_printed < PRINT_FIRST_N_MATCHES:
                        print(f"  MATCH -> ID: {vector_id}")
                        print(f"           metadata[{FIELD_NAME}] = {metadata.get(FIELD_NAME)}")
                        examples_printed += 1

            print(f"           Matches en este batch: {batch_matches}")
            print(f"           Matches acumulados   : {matched_vectors}\n")

    except Exception as e:
        print("ERROR durante el recorrido del indice:")
        print(str(e))
        return

    elapsed = time.time() - start_time

    print("=====================================================")
    print("RESULTADOS FINALES")
    print("=====================================================")
    print(f"Total de vectores recorridos             : {total_vectors}")
    print(f"Vectores con {FIELD_NAME}={TARGET_VALUE} : {matched_vectors}")

    if total_vectors > 0:
        percent = (matched_vectors / total_vectors) * 100
        print(f"Porcentaje                              : {percent:.2f}%")

    print(f"Tiempo total                            : {elapsed:.2f} segundos")
    print("=====================================================")

    if SAVE_MATCHED_IDS:
        output_data = {
            "index_host": INDEX_HOST,
            "namespace": NAMESPACE,
            "field_name": FIELD_NAME,
            "target_value": TARGET_VALUE,
            "total_vectors": total_vectors,
            "matched_vectors": matched_vectors,
            "matched_ids": matched_ids
        }

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        print(f"\nArchivo generado: {OUTPUT_FILE}")

    return {
        "total_vectors": total_vectors,
        "matched_vectors": matched_vectors,
        "matched_ids": matched_ids
    }


if __name__ == "__main__":
    count_and_list_vectors()