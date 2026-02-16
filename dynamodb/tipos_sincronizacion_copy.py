import re
import json
import boto3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo  # Python 3.9+

# =========================
# Config
# =========================

# prod
#KB_ID = "ZLSIIBQ6B3"
#DS_ID = "GERVMMQQKG"

KB_ID = "ZLSIIBQ6B3"
#DS_ID = "4FQEKRDVOD" 
DS_ID = "GERVMMQQKG"
REGION = "us-west-2"
GT_TZ = ZoneInfo("America/Guatemala")

OUTPUT_FILE = "ingestion_errors_report.txt"

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
            # Sometimes AWS sends a string that itself is a JSON list of strings
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
    # Conservative match: "s3://bucket/key"
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

def categorize_reason(reason: str) -> str:
    """
    Heuristic categories so you can quickly see what kind of failures you have.
    Adjust / add patterns as you discover new ones in your environment.
    """
    s = (reason or "").lower()

    # Your original
    if "no text content found" in s:
        return "TEXT_EMPTY"

    # Common classes
    if "accessdenied" in s or "access denied" in s or "403" in s:
        return "ACCESS_DENIED"
    if "nosuchkey" in s or "not found" in s or "404" in s:
        return "NOT_FOUND"
    if "throttl" in s or "rate exceeded" in s or "too many requests" in s:
        return "THROTTLED"
    if "timeout" in s or "timed out" in s:
        return "TIMEOUT"
    if "validation" in s or "invalid" in s:
        return "VALIDATION_ERROR"
    if "unsupported" in s or "not supported" in s:
        return "UNSUPPORTED_FORMAT"
    if "malformed" in s or "parse" in s or "parsing" in s or "could not read" in s:
        return "PARSE_ERROR"
    if "encryption" in s or "kms" in s or "encrypted" in s:
        return "ENCRYPTION_KMS"
    if "virus" in s or "malware" in s:
        return "MALWARE_FLAG"
    if "internalerror" in s or "internal error" in s or "service unavailable" in s or "500" in s:
        return "SERVICE_ERROR"

    return "OTHER"

def dedupe_preserve_order(items):
    return list(dict.fromkeys(items))

# =========================
# Main
# =========================

latest = get_latest_job_summary()
if not latest:
    print("No ingestion jobs found for this data source.")
    raise SystemExit(0)

latest_status = latest.get("status")
latest_job_id = latest.get("ingestionJobId")

# If latest job is IN_PROGRESS, use the most recent COMPLETED job instead.
if latest_status == "IN_PROGRESS":
    job_id = get_latest_completed_job_id()
    if not job_id:
        print("Latest job is IN_PROGRESS, and no COMPLETED ingestion jobs were found.")
        raise SystemExit(0)
    selected_reason = "latest job IN_PROGRESS -> using latest COMPLETED"
else:
    job_id = latest_job_id
    selected_reason = f"using latest job (status={latest_status})"

detail = client.get_ingestion_job(
    knowledgeBaseId=KB_ID,
    dataSourceId=DS_ID,
    ingestionJobId=job_id
)["ingestionJob"]

# Normalize reasons
reasons = normalize_failure_reasons(detail.get("failureReasons", []) or [])

# Build categorized report
by_category = {}       # category -> list of reasons (raw)
files_by_category = {} # category -> list of s3 uris
all_files = []

for r in reasons:
    cat = categorize_reason(r)
    by_category.setdefault(cat, []).append(r)

    uris = extract_s3_uris(r)
    if uris:
        files_by_category.setdefault(cat, []).extend(uris)
        all_files.extend(uris)

# Dedupe files per category + global
for cat in list(files_by_category.keys()):
    files_by_category[cat] = dedupe_preserve_order(files_by_category[cat])
all_files = dedupe_preserve_order(all_files)

# Guatemala timestamps
generated_at_gt = datetime.now(GT_TZ).strftime("%Y-%m-%d %H:%M:%S")
started_at_gt = to_gt_str(detail.get("startedAt"))
updated_at_gt = to_gt_str(detail.get("updatedAt"))

# Write report
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write("BEDROCK KB INGESTION - FAILURE REASONS REPORT\n")
    f.write("============================================\n\n")

    f.write(f"GeneratedAt GT : {generated_at_gt} (America/Guatemala)\n")
    f.write(f"KnowledgeBaseId: {KB_ID}\n")
    f.write(f"DataSourceId   : {DS_ID}\n")
    f.write(f"Selected       : {selected_reason}\n")
    f.write(f"IngestionJobId : {job_id}\n")
    f.write(f"Status         : {detail.get('status')}\n")
    f.write(f"StartedAt GT   : {started_at_gt}\n")
    f.write(f"UpdatedAt GT   : {updated_at_gt}\n")

    f.write("\n--------------------------------------------\n")
    f.write("SUMMARY BY CATEGORY\n")
    f.write("--------------------------------------------\n")

    total_reasons = sum(len(v) for v in by_category.values())
    f.write(f"Total failureReasons: {total_reasons}\n")
    f.write(f"Total unique files  : {len(all_files)}\n\n")

    # Sort categories by count desc
    cats_sorted = sorted(by_category.items(), key=lambda kv: len(kv[1]), reverse=True)
    for cat, arr in cats_sorted:
        f.write(f"- {cat}: {len(arr)}\n")

    f.write("\n--------------------------------------------\n")
    f.write("DETAIL (per category)\n")
    f.write("--------------------------------------------\n\n")

    for cat, arr in cats_sorted:
        f.write(f"[{cat}] ({len(arr)} reasons)\n")

        uris = files_by_category.get(cat, [])
        if uris:
            f.write(f"FILES ({len(uris)} unique):\n")
            for u in uris:
                f.write(f"  - {u}\n")
        else:
            f.write("FILES: (none detected in failureReasons)\n")

        f.write("\nREASONS:\n")
        for i, reason in enumerate(arr, start=1):
            f.write(f"  {i}. {reason}\n")
        f.write("\n" + ("-" * 44) + "\n\n")

print(f"✔ Report written to {OUTPUT_FILE} "
      f"({sum(len(v) for v in by_category.values())} reasons, {len(all_files)} unique files) "
      f"[Guatemala time]")
