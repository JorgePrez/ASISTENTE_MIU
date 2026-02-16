import re
import boto3
from datetime import datetime, timezone

KB_ID = "B0J6EB9XUO"
DS_ID = "WKSWJ0IDZB"
REGION = "us-west-2"

client = boto3.client("bedrock-agent", region_name=REGION)

def extract_s3_uris(text: str):
    return re.findall(r"s3://[^\s,\]]+", text)

def pick_dt(summary: dict) -> datetime:
    """
    Pick the best available datetime from a job summary.
    Falls back to epoch if none found.
    """
    for k in ("updatedAt", "startedAt", "createdAt"):
        v = summary.get(k)
        if isinstance(v, datetime):
            return v
    return datetime(1970, 1, 1, tzinfo=timezone.utc)

# 1) List jobs (the API usually returns newest-first, but we won't assume it)
resp = client.list_ingestion_jobs(
    knowledgeBaseId=KB_ID,
    dataSourceId=DS_ID,
    maxResults=50,
)

jobs = resp.get("ingestionJobSummaries", [])
if not jobs:
    print("No ingestion jobs found for this data source.")
    raise SystemExit(0)

# 2) Pick the most recent job by timestamp
latest = max(jobs, key=pick_dt)
latest_job_id = latest["ingestionJobId"]

# 3) Fetch details for only the latest job
detail = client.get_ingestion_job(
    knowledgeBaseId=KB_ID,
    dataSourceId=DS_ID,
    ingestionJobId=latest_job_id
)["ingestionJob"]

print("=== Latest Ingestion Job ===")
print("ingestionJobId :", latest_job_id)
print("status         :", detail.get("status"))
print("startedAt      :", detail.get("startedAt"))
print("updatedAt      :", detail.get("updatedAt"))
print("statistics     :", detail.get("statistics"))
print()

# 4) Extract PDF files that were ignored due to no text content
pdf_hits = []
failure_reasons = detail.get("failureReasons", []) or []

for reason in failure_reasons:
    reason_l = reason.lower()
    if "no text content found" in reason_l:
        for uri in extract_s3_uris(reason):
            if uri.lower().endswith(".pdf"):
                pdf_hits.append({
                    "ingestionJobId": latest_job_id,
                    "pdf_s3_uri": uri,
                    "reason": reason
                })

print("=== PDF hits (no text content found) ===")
print(f"count: {len(pdf_hits)}")
for item in pdf_hits:
    print("-", item["pdf_s3_uri"])

# If you still want the raw list object:
# print(pdf_hits)
