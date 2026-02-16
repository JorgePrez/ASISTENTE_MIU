import json
import requests
import csv
from typing import List, Dict, Any

API_ORIGEN = "https://miu.ufm.edu/asistente_documentos_api.php"

# Pinecone
PINECONE_API_KEY = "pcsk_i8GnP_JEpQMBkWnne9ggLiygRHZnx871pCmKgWpZCjh46oH8JhGvPToUoMAN6KTvp9NkL"
INDEX_HOST = "miu-documentos-vz16bim.svc.apw5-4e34-81fa.pinecone.io"
NAMESPACE = "namespace "  #  espacio final
DIMENSION = 1536

USER_AGENT_FIREFOX = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) "
    "Gecko/20100101 Firefox/122.0"
)

def fetch_docs() -> List[Dict[str, Any]]:
    data = {
        "buscarDocumentosCursoPDFSINPROCESAR": "1",
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
    vector = [0.0] * DIMENSION
    
    found_count = 0
    not_found_count = 0
    
    with open('pinecone_results_found.csv', 'w', newline='', encoding='utf-8') as found_file, \
         open('pinecone_results_not_found.csv', 'w', newline='', encoding='utf-8') as not_found_file:
        
        found_writer = csv.writer(found_file)
        not_found_writer = csv.writer(not_found_file)
        
        found_writer.writerow(['MIU_DOCUMENTOS', 'PATH_ADUNTO'])
        not_found_writer.writerow(['MIU_DOCUMENTOS', 'PATH_ADUNTO'])
        found_file.flush()
        not_found_file.flush()
        
        for d in docs:
            miu = d.get("MIU_DOCUMENTOS")
            path = d.get("PATH_ADUNTO")

            if miu is None or path is None:
                continue

            miu_str = str(miu)

            try:
                existe = pinecone_exists(miu_str, vector)
                if existe:
                    found_writer.writerow([miu_str, str(path)])
                    found_file.flush()
                    found_count += 1
                else:
                    not_found_writer.writerow([miu_str, str(path)])
                    not_found_file.flush()
                    not_found_count += 1
            except requests.HTTPError as e:
                print(f"[WARN] Error consultando Pinecone para MIU_DOCUMENTOS={miu_str}: {e}")
                not_found_writer.writerow([miu_str, str(path)])
                not_found_file.flush()
                not_found_count += 1

    with open('pinecone_results_totals.csv', 'w', newline='', encoding='utf-8') as totals_file:
        totals_writer = csv.writer(totals_file)
        totals_writer.writerow(['CATEGORIA', 'TOTAL'])
        totals_writer.writerow(['ENCONTRADOS', found_count])
        totals_writer.writerow(['NO_ENCONTRADOS', not_found_count])
        totals_writer.writerow(['TOTAL_PROCESADOS', found_count + not_found_count])

    with open('pinecone_results_no_procesados.csv', 'w', newline='', encoding='utf-8') as no_procesados_file:
        no_procesados_writer = csv.writer(no_procesados_file)
        no_procesados_writer.writerow(['NO_PROCESADOS'])
        no_procesados_writer.writerow([not_found_count])

    print("CSVs generados: pinecone_results_found.csv, pinecone_results_not_found.csv, pinecone_results_totals.csv y pinecone_results_no_procesados.csv")

if __name__ == "__main__":
    main()
