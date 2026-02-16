import re
import json
import boto3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo  # Python 3.9+

# =========================
# Config
# =========================

# compras
KB_ID = "B0J6EB9XUO"
DS_ID = "WKSWJ0IDZB"




# prod
#KB_ID = "ZLSIIBQ6B3"
#DS_ID = "4FQEKRDVOD"

REGION = "us-west-2"
GT_TZ = ZoneInfo("America/Guatemala")

TARGET_PHRASE = "no text content found in the files"
OUTPUT_FILE = "pdfs_no_text_content.txt"

client = boto3.client("bedrock-agent", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)

# =========================
# Helpers
# =========================

def normalize_failure_reasons(failure_reasons):
    out = []
    for r in (failure_reasons or []):
        if isinstance(r, str):
            s = r.strip()
            if s.startswith("[") and s.endswith("]"):
                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, list):
                        out.extend(parsed)
                        continue
                except Exception:
                    pass
            out.append(r)
        else:
            out.append(str(r))
    return out

def extract_s3_uris(text: str):
    return re.findall(r"s3://[^\s,\]]+", text)

def to_gt_str(dt_obj):
    if not dt_obj:
        return "—"
    if isinstance(dt_obj, datetime):
        if dt_obj.tzinfo is None:
            dt_obj = dt_obj.replace(tzinfo=timezone.utc)
        return dt_obj.astimezone(GT_TZ).strftime("%Y-%m-%d %H:%M:%S")
    return str(dt_obj)

def list_jobs_sorted(max_results=50, next_token=None):
    kwargs = dict(
        knowledgeBaseId=KB_ID,
        dataSourceId=DS_ID,
        sortBy={"attribute": "STARTED_AT", "order": "DESCENDING"},
        maxResults=max_results,
    )
    if next_token:
        kwargs["nextToken"] = next_token
    return client.list_ingestion_jobs(**kwargs)

def pick_latest_finished_job_id():
    next_token = None
    while True:
        resp = list_jobs_sorted(50, next_token)
        jobs = resp.get("ingestionJobSummaries", [])
        for j in jobs:
            if j.get("status") != "IN_PROGRESS":
                return j["ingestionJobId"], j["status"]
        next_token = resp.get("nextToken")
        if not next_token:
            break
    return None, None

def parse_s3_uri(uri):
    no_scheme = uri[5:]
    bucket, key = no_scheme.split("/", 1)
    return bucket, key

def s3_object_exists(bucket, key):
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except s3.exceptions.ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            return False
        raise

# =========================
# Main
# =========================

latest = list_jobs_sorted(1).get("ingestionJobSummaries", [])
if not latest:
    print("No ingestion jobs found.")
    raise SystemExit(0)

latest = latest[0]

if latest["status"] == "IN_PROGRESS":
    job_id, picked_status = pick_latest_finished_job_id()
    if not job_id:
        print("Latest job IN_PROGRESS and no finished jobs found.")
        raise SystemExit(0)
else:
    job_id = latest["ingestionJobId"]
    picked_status = latest["status"]

detail = client.get_ingestion_job(
    knowledgeBaseId=KB_ID,
    dataSourceId=DS_ID,
    ingestionJobId=job_id
)["ingestionJob"]

warnings = normalize_failure_reasons(detail.get("failureReasons", []))
filtered = [w for w in warnings if TARGET_PHRASE in w.lower()]

# PDFs con error
pdfs = []
for w in filtered:
    for uri in extract_s3_uris(w):
        if uri.lower().endswith(".pdf"):
            pdfs.append(uri)

pdfs = list(dict.fromkeys(pdfs))

# 🔥 SOLO conservar PDFs que SÍ tienen metadata
final_pdfs = []

for pdf_uri in pdfs:
    bucket, pdf_key = parse_s3_uri(pdf_uri)
    meta_key = f"{pdf_key}.metadata.json"
    if s3_object_exists(bucket, meta_key):
        final_pdfs.append(pdf_uri)

# =========================
# Write TXT (SALIDA LIMPIA)
# =========================

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write("PDFs SIN TEXTO (con metadata existente)\n")
    f.write("======================================\n\n")

    f.write(f"GeneratedAt GT : {datetime.now(GT_TZ).strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"KnowledgeBaseId: {KB_ID}\n")
    f.write(f"DataSourceId   : {DS_ID}\n")
    f.write(f"IngestionJobId : {job_id}\n")
    f.write(f"Status         : {detail.get('status')} ({picked_status})\n")
    f.write(f"StartedAt GT   : {to_gt_str(detail.get('startedAt'))}\n")
    f.write(f"UpdatedAt GT   : {to_gt_str(detail.get('updatedAt'))}\n")
    f.write("\n--------------------------------------\n\n")

    f.write(f"TOTAL FILES: {len(final_pdfs)}\n\n")
    f.write("FILES:\n")

    for uri in final_pdfs:
        f.write(f"- {uri}\n")

print(f"✔ TXT generado: {OUTPUT_FILE} ({len(final_pdfs)} archivos)")


## 