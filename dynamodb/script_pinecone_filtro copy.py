import json
import requests
from typing import List, Dict, Any

API_ORIGEN = "https://miu.ufm.edu/asistente_documentos_api.php"

# Pinecone
PINECONE_API_KEY = "pcsk_i8GnP_JEpQMBkWnne9ggLiygRHZnx871pCmKgWpZCjh46oH8JhGvPToUoMAN6KTvp9NkL"
INDEX_HOST = "miu-documentos-vz16bim.svc.apw5-4e34-81fa.pinecone.io"
NAMESPACE = "namespace "  # ⚠️ con espacio final
DIMENSION = 1536

USER_AGENT_FIREFOX = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) "
    "Gecko/20100101 Firefox/122.0"
)

def fetch_docs() -> List[Dict[str, Any]]:
    """
    POST al API origen, devuelve lista de docs.
    """
    data = {
        "buscarDocumentosCursoPDFSINPROCESAR": "1",
        # "curso_impartido": "138181",  # opcional si tu API lo soporta
    }
    headers = {
        "User-Agent": USER_AGENT_FIREFOX,
        "Accept": "application/json",
    }

    resp = requests.post(API_ORIGEN, data=data, headers=headers, timeout=30)
    resp.raise_for_status()

    try:
        payload = resp.json()
    except Exception:
        raise RuntimeError(f"Respuesta no es JSON. Raw: {resp.text[:500]}")

    if not isinstance(payload, list):
        raise RuntimeError(f"Se esperaba un JSON array, vino: {type(payload)}")

    return payload


def pinecone_exists(miu_documentos: str, vector: List[float]) -> bool:
    """
    Consulta Pinecone por filtro metadata miu_documentos.
    Retorna True si hay matches.
    """
    url = f"https://{INDEX_HOST}/query"
    body = {
        "vector": vector,
        "namespace": NAMESPACE,
        "topK": 1,
        "includeMetadata": False,
        "includeValues": False,
        "filter": {
            "miu_documentos": str(miu_documentos)
        }
    }
    headers = {
        "Api-Key": PINECONE_API_KEY,
        "Content-Type": "application/json",
        "X-Pinecone-API-Version": "2025-04",
    }

    resp = requests.post(url, headers=headers, json=body, timeout=20)
    resp.raise_for_status()

    data = resp.json()
    matches = data.get("matches", [])
    return isinstance(matches, list) and len(matches) > 0


def main():
    docs = fetch_docs()

    # vector dummy (una sola vez)
    vector = [0.0] * DIMENSION

    no_existen: List[Dict[str, str]] = []

    for d in docs:
        miu = d.get("MIU_DOCUMENTOS")
        path = d.get("PATH_ADUNTO")

        if miu is None or path is None:
            continue

        miu_str = str(miu)

        try:
            existe = pinecone_exists(miu_str, vector)
        except requests.HTTPError as e:
            # Si querés, podés decidir qué hacer ante error de Pinecone
            # aquí lo reporto y continuo
            print(f"[WARN] Error consultando Pinecone para MIU_DOCUMENTOS={miu_str}: {e}")
            continue

        if not existe:
            no_existen.append({
                "MIU_DOCUMENTOS": miu_str,
                "PATH_ADUNTO": str(path),
            })

    output = {
        "success": True,
        "total": len(no_existen),
        "data": no_existen
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
