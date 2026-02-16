import re
import json
import boto3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo  # Python 3.9+

# =========================
# Config
# =========================

# compras
# KB_ID = "B0J6EB9XUO"
# DS_ID = "WKSWJ0IDZB"

# prod
KB_ID = "ZLSIIBQ6B3"
DS_ID = "4FQEKRDVOD"

REGION = "us-west-2"
GT_TZ = ZoneInfo("America/Guatemala")

TARGET_PHRASE = "no text content found in the files"
OUTPUT_FILE = "pdfs_no_text_content.txt"

client = boto3.client("bedrock-agent", region_name=REGION)

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
    boto3 typically returns tz-aware datetimes; we handle both.
    """
    if not dt_obj:
        return "—"
    if isinstance(dt_obj, datetime):
        if dt_obj.tzinfo is None:
            # Assume UTC if AWS returned naive (rare), to avoid wrong GT time
            dt_obj = dt_obj.replace(tzinfo=timezone.utc)
        return dt_obj.astimezone(GT_TZ).strftime("%Y-%m-%d %H:%M:%S")
    return str(dt_obj)

def get_latest_job_summary():
    """
    Returns the most recent ingestion job summary (any status), or None.
    """
    resp = client.list_ingestion_jobs(
        knowledgeBaseId=KB_ID,
        dataSourceId=DS_ID,
        sortBy={"attribute": "STARTED_AT", "order": "DESCENDING"},
        maxResults=1,
    )
    jobs = resp.get("ingestionJobSummaries", [])
    return jobs[0] if jobs else None

def get_latest_completed_job_id():
    """
    Returns ingestionJobId for the most recent job with STATUS == COMPLETE, else None.
    """
    resp = client.list_ingestion_jobs(
        knowledgeBaseId=KB_ID,
        dataSourceId=DS_ID,
        filters=[{"attribute": "STATUS", "operator": "EQ", "values": ["COMPLETE"]}],
        sortBy={"attribute": "STARTED_AT", "order": "DESCENDING"},
        maxResults=1,
    )
    jobs = resp.get("ingestionJobSummaries", [])
    if not jobs:
        return None
    return jobs[0]["ingestionJobId"]

# =========================
# Main
# =========================

latest = get_latest_job_summary()
if not latest:
    print("No ingestion jobs found for this data source.")
    raise SystemExit(0)

latest_status = latest.get("status")
latest_job_id = latest.get("ingestionJobId")

# ✅ Change requested:
# If the latest job is IN_PROGRESS, use the most recent COMPLETED job instead.
if latest_status == "IN_PROGRESS":
    job_id = get_latest_completed_job_id()
    if not job_id:
        print("Latest job is IN_PROGRESS, and no COMPLETED ingestion jobs were found.")
        raise SystemExit(0)
    selected_reason = "latest job IN_PROGRESS -> using latest COMPLETED"
else:
    # If latest is not IN_PROGRESS, use it (even if FAILED/STOPPED/etc.)
    job_id = latest_job_id
    selected_reason = f"using latest job (status={latest_status})"

detail = client.get_ingestion_job(
    knowledgeBaseId=KB_ID,
    dataSourceId=DS_ID,
    ingestionJobId=job_id
)["ingestionJob"]

# Normalize warnings
warnings = normalize_failure_reasons(detail.get("failureReasons", []) or [])

# Filter ONLY "no text content found"
filtered = [w for w in warnings if TARGET_PHRASE in w.lower()]

# Extract ALL PDF files from the filtered warnings
pdf_files = []
for w in filtered:
    for uri in extract_s3_uris(w):
        if uri.lower().endswith(".pdf"):
            pdf_files.append(uri)

# Deduplicate while preserving order
pdf_files = list(dict.fromkeys(pdf_files))
total_pdfs = len(pdf_files)

# Guatemala timestamps
generated_at_gt = datetime.now(GT_TZ).strftime("%Y-%m-%d %H:%M:%S")
started_at_gt = to_gt_str(detail.get("startedAt"))
updated_at_gt = to_gt_str(detail.get("updatedAt"))

# Write summary TXT (everything in Guatemala time)
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write("PDFs SIN TEXTO (no text content found)\n")
    f.write("===================================\n\n")

    f.write(f"GeneratedAt GT : {generated_at_gt} (America/Guatemala)\n")
    f.write(f"KnowledgeBaseId: {KB_ID}\n")
    f.write(f"DataSourceId   : {DS_ID}\n")
    f.write(f"Selected       : {selected_reason}\n")
    f.write(f"IngestionJobId : {job_id}\n")
    f.write(f"Status         : {detail.get('status')}\n")
    f.write(f"StartedAt GT   : {started_at_gt}\n")
    f.write(f"UpdatedAt GT   : {updated_at_gt}\n")
    f.write("\n-----------------------------------\n\n")

    f.write(f"TOTAL FILES: {total_pdfs}\n\n")
    f.write("FILES:\n")
    for uri in pdf_files:
        f.write(f"- {uri}\n")

print(f"✔ PDF list written to {OUTPUT_FILE} ({total_pdfs} files) [Guatemala time]")
