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
    """
    Flatten failureReasons into a plain list[str].
    Handles the case where AWS returns one string containing a JSON array of strings.
    """
    out = []
    for r in (failure_reasons or []):
        if isinstance(r, str):
            s = r.strip()
            if s.startswith("[") and s.endswith("]"):
                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
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
    """
    Convert a datetime (possibly naive) to Guatemala time string.
    """
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
    """
    Returns the most recent ingestion job that is NOT IN_PROGRESS.
    This avoids guessing exact terminal status names.
    """
    next_token = None
    while True:
        resp = list_jobs_sorted(max_results=50, next_token=next_token)
        jobs = resp.get("ingestionJobSummaries", []) or []

        for j in jobs:
            st = j.get("status")
            if st and st != "IN_PROGRESS":
                return j.get("ingestionJobId"), st

        next_token = resp.get("nextToken")
        if not next_token:
            break

    return None, None

def parse_s3_uri(s3_uri: str):
    """
    Parse s3://bucket/key into (bucket, key)
    """
    if not s3_uri.startswith("s3://"):
        raise ValueError(f"Invalid S3 URI: {s3_uri}")
    no_scheme = s3_uri[5:]
    parts = no_scheme.split("/", 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ""
    return bucket, key

def metadata_key_for_pdf_key(pdf_key: str) -> str:
    # 요구: same name + ".metadata.json"
    return f"{pdf_key}.metadata.json"

def s3_object_exists(bucket: str, key: str) -> bool:
    """
    HEAD the object. True if exists, False if 404/NoSuchKey.
    Raises for other errors (permissions, etc.) so you notice.
    """
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except s3.exceptions.ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        # Common "not found" codes
        if code in ("404", "NoSuchKey", "NotFound"):
            return False
        # If AccessDenied or others, bubble up (important for debugging)
        raise

# =========================
# Main
# =========================

# 1) Look at the latest job (for debug)
first_page = list_jobs_sorted(max_results=1)
latest_jobs = first_page.get("ingestionJobSummaries", []) or []
if not latest_jobs:
    print("No ingestion jobs found for this data source.")
    raise SystemExit(0)

latest = latest_jobs[0]
latest_job_id = latest.get("ingestionJobId")
latest_status = latest.get("status")

# 2) If latest is IN_PROGRESS, find latest NOT IN_PROGRESS
if latest_status == "IN_PROGRESS":
    job_id, picked_status = pick_latest_finished_job_id()
    if not job_id:
        print("Latest job is IN_PROGRESS, and no finished (non-IN_PROGRESS) jobs were found.")
        raise SystemExit(0)
    selected_reason = f"latest job IN_PROGRESS ({latest_job_id}) -> using latest finished ({picked_status})"
else:
    job_id = latest_job_id
    picked_status = latest_status
    selected_reason = f"using latest job (status={latest_status})"

# 3) Get job details
detail = client.get_ingestion_job(
    knowledgeBaseId=KB_ID,
    dataSourceId=DS_ID,
    ingestionJobId=job_id
)["ingestionJob"]

# 4) Normalize + filter warnings
warnings = normalize_failure_reasons(detail.get("failureReasons", []) or [])
filtered = [w for w in warnings if TARGET_PHRASE in w.lower()]

# 5) Extract PDFs
pdf_files = []
for w in filtered:
    for uri in extract_s3_uris(w):
        if uri.lower().endswith(".pdf"):
            pdf_files.append(uri)

pdf_files = list(dict.fromkeys(pdf_files))
total_pdfs = len(pdf_files)

# 6) For each PDF, check if "pdf.metadata.json" exists
pdf_with_metadata = []   # list of dicts: {pdf_uri, metadata_uri, exists}
meta_exists_count = 0

for pdf_uri in pdf_files:
    bucket, pdf_key = parse_s3_uri(pdf_uri)
    meta_key = metadata_key_for_pdf_key(pdf_key)
    meta_uri = f"s3://{bucket}/{meta_key}"

    exists = s3_object_exists(bucket, meta_key)
    if exists:
        meta_exists_count += 1

    pdf_with_metadata.append({
        "pdf_uri": pdf_uri,
        "metadata_uri": meta_uri,
        "metadata_exists": exists,
    })

# 7) Guatemala timestamps
generated_at_gt = datetime.now(GT_TZ).strftime("%Y-%m-%d %H:%M:%S")
started_at_gt = to_gt_str(detail.get("startedAt"))
updated_at_gt = to_gt_str(detail.get("updatedAt"))

# 8) Write TXT
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write("PDFs SIN TEXTO (no text content found)\n")
    f.write("===================================\n\n")

    f.write(f"GeneratedAt GT : {generated_at_gt} (America/Guatemala)\n")
    f.write(f"KnowledgeBaseId: {KB_ID}\n")
    f.write(f"DataSourceId   : {DS_ID}\n")
    f.write(f"Selected       : {selected_reason}\n")
    f.write(f"IngestionJobId : {job_id}\n")
    f.write(f"Status         : {detail.get('status')} (picked_status={picked_status})\n")
    f.write(f"StartedAt GT   : {started_at_gt}\n")
    f.write(f"UpdatedAt GT   : {updated_at_gt}\n")
    f.write("\n-----------------------------------\n\n")

    f.write(f"TOTAL FILES: {total_pdfs}\n")
    f.write(f"WITH METADATA (.pdf.metadata.json): {meta_exists_count}\n\n")

    f.write("FILES:\n")
    for item in pdf_with_metadata:
        mark = "YES" if item["metadata_exists"] else "NO"
        f.write(f"- {item['pdf_uri']}  | metadata: {mark}\n")

    f.write("\n\nFILES WITH METADATA:\n")
    for item in pdf_with_metadata:
        if item["metadata_exists"]:
            f.write(f"- {item['pdf_uri']}\n  -> {item['metadata_uri']}\n")

print(f"✔ TXT written to {OUTPUT_FILE} ({total_pdfs} PDFs, metadata YES: {meta_exists_count}) [Guatemala time]")
