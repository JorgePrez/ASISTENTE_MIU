import json
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List

# =========================
# CONFIG
# =========================
INPUT_JSON = "documentos.json"
MAX_WORKERS = 15  # ⚠️ ajustable (10–20 seguro)

# Pinecone
PINECONE_API_KEY = "pcsk_i8GnP_JEpQMBkWnne9ggLiygRHZnx871pCmKgWpZCjh46oH8JhGvPToUoMAN6KTvp9NkL"
INDEX_HOST = "miu-documentos-vz16bim.svc.apw5-4e34-81fa-pinecone.io"
NAMESPACE = "namespace "  # ⚠️ espacio final
DIMENSION = 1536

QUERY_URL = f"https://{INDEX_HOST}/query"

HEADERS = {
    "Api-Key": PINECONE_API_KEY,
    "Content-Type": "application/json",
    "X-Pinecone-API-Version": "2025-04",
}

# Vector dummy (una sola vez)
VECTOR = [0.0] * DIMENSION


# =========================
# FUNCIONES
# =========================
def existe_en_pinecone(doc: Dict) -> Dict | None:
    """
    Retorna el doc SOLO si NO existe en Pinecone.
    Si existe, retorna None.
    """
    miu = str(doc.get("MIU_DOCUMENTOS", "")).strip()
    path = doc.get("PATH_ADUNTO")

    if not miu or not path:
        return None

    body = {
        "vector": VECTOR,
        "namespace": NAMESPACE,
        "topK": 1,
        "includeMetadata": False,
        "includeValues": False,
        "filter": {
            "miu_documentos": miu
        }
    }

    try:
        r = requests.post(
            QUERY_URL,
            headers=HEADERS,
            json=body,
            timeout=15
        )
        r.raise_for_status()
        data = r.json()
        matches = data.get("matches", [])

        # 👉 NO existe en Pinecone
        if not matches:
            return {
                "MIU_DOCUMENTOS": miu,
                "PATH_ADUNTO": path
            }

    except Exception as e:
        # Si querés, acá podés loggear errores
        print(f"[WARN] Pinecone error MIU_DOCUMENTOS={miu}: {e}")

    return None


# =========================
# MAIN
# =========================
def main():
    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        documentos: List[Dict] = json.load(f)

    no_existen: List[Dict] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(existe_en_pinecone, d) for d in documentos]

        for future in as_completed(futures):
            result = future.result()
            if result:
                no_existen.append(result)

    output = {
        "success": True,
        "total": len(no_existen),
        "data": no_existen
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
