import requests

# ======================
# Config
# ======================
PINECONE_API_KEY = "pcsk_i8GnP_JEpQMBkWnne9ggLiygRHZnx871pCmKgWpZCjh46oH8JhGvPToUoMAN6KTvp9NkL"
INDEX_HOST = "miu-documentos-vz16bim.svc.apw5-4e34-81fa.pinecone.io"
NAMESPACE = "namespace "
DIMENSION = 1536

URL = f"https://{INDEX_HOST}/query"

HEADERS = {
    "Api-Key": PINECONE_API_KEY,
    "Content-Type": "application/json",
    "X-Pinecone-API-Version": "2025-04",
}

# Vector dummy (1536 ceros)
VECTOR_DUMMY = [0.0] * DIMENSION


# ======================
# 1) EXISTE → 995663
# ======================
body_existente = {
    "vector": VECTOR_DUMMY,
    "namespace": NAMESPACE,
    "topK": 1,
    "includeMetadata": False,
    "includeValues": False,
    "filter": {
        "miu_documentos": "995663"
    }
}

resp1 = requests.post(URL, headers=HEADERS, json=body_existente, timeout=20)
resp1.raise_for_status()

data1 = resp1.json()
print("Resultado para MIU_DOCUMENTOS = 995663")
print("matches:", data1.get("matches"))
print("-" * 60)


# ======================
# 2) NO EXISTE → 998130
# ======================
body_no_existente = {
    "vector": VECTOR_DUMMY,
    "namespace": NAMESPACE,
    "topK": 1,
    "includeMetadata": False,
    "includeValues": False,
    "filter": {
        "miu_documentos": "998130"
    }
}

resp2 = requests.post(URL, headers=HEADERS, json=body_no_existente, timeout=20)
resp2.raise_for_status()

data2 = resp2.json()
print("Resultado para MIU_DOCUMENTOS = 998130")
print("matches:", data2.get("matches"))
print("-" * 60)
