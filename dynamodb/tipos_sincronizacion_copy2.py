import re
import json
import boto3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo  # Python 3.9+

# =========================
# Config
# =========================

KB_ID = "ZLSIIBQ6B3"
DS_ID = "GERVMMQQKG"
REGION = "us-west-2"
GT_TZ = ZoneInfo("America/Guatemala")

OUTPUT_FILE = "tipo_sincronizacionlast10.txt"

# Si querés seguir sacando solo PDFs de cierto error, dejalo.
# Pero ahora el reporte incluirá TODAS las clases de error.
TARGET_PHRASE = "no text content found in the files"

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
    if not dt_obj:
        return "—"
    if isinstance(dt_obj, datetime):
        if dt_obj.tzinfo is None:
            dt_obj = dt_obj.replace(tzinfo=timezone.utc)
        return dt_obj.astimezone(GT_TZ).strftime("%Y-%m-%d %H:%M:%S")
    return str(dt_obj)

def get_last_n_job_summaries(n=10):
    resp = client.list_ingestion_jobs(
        knowledgeBaseId=KB_ID,
        dataSourceId=DS_ID,
        sortBy={"attribute": "STARTED_AT", "order": "DESCENDING"},
        maxResults=n,
    )
    return resp.get("ingestionJobSummaries", []) or []

def select_job_from_last10(job_summaries):
    """
    If the latest job is IN_PROGRESS, choose the first finished job
    among the last 10: COMPLETE/FAILED/STOPPED.
    Otherwise choose the latest job (even if FAILED/STOPPED/etc).
    """
    if not job_summaries:
        return None, "no jobs found"

    latest = job_summaries[0]
    latest_status = (latest.get("status") or "").upper()

    if latest_status == "IN_PROGRESS":
        for j in job_summaries[1:]:  # skip latest (running)
            st = (j.get("status") or "").upper()
            if st in ("COMPLETE", "FAILED", "STOPPED"):
                return j.get("ingestionJobId"), "latest IN_PROGRESS -> using first finished in last 10"
        # If none found in last 10, last resort: just use latest anyway
        return latest.get("ingestionJobId"), "latest IN_PROGRESS -> no finished job in last 10, using latest anyway"

    return latest.get("ingestionJobId"), f"using latest job (status={latest_status})"

def categorize_reason(reason: str) -> str:
    s = (reason or "").lower()

    if "no text content found" in s:
        return "TEXT_EMPTY"
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
    if "internalerror" in s or "internal error" in s or "service unavailable" in s or "500" in s:
        return "SERVICE_ERROR"

    return "OTHER"

def dedupe_preserve_order(items):
    return list(dict.fromkeys(items))

# =========================
# Main
# =========================

jobs10 = get_last_n_job_summaries(10)
if not jobs10:
    print("No ingestion jobs found for this data source.")
    raise SystemExit(0)

job_id, selected_reason = select_job_from_last10(jobs10)
if not job_id:
    print("Could not select a job id from last 10.")
    raise SystemExit(0)

detail = client.get_ingestion_job(
    knowledgeBaseId=KB_ID,
    dataSourceId=DS_ID,
    ingestionJobId=job_id
)["ingestionJob"]

reasons = normalize_failure_reasons(detail.get("failureReasons", []) or [])

# Categorize + collect files
by_category = {}
files_by_category = {}

for r in reasons:
    cat = categorize_reason(r)
    by_category.setdefault(cat, []).append(r)

    uris = extract_s3_uris(r)
    if uris:
        files_by_category.setdefault(cat, []).extend(uris)

for cat in list(files_by_category.keys()):
    files_by_category[cat] = dedupe_preserve_order(files_by_category[cat])

# Guatemala timestamps
generated_at_gt = datetime.now(GT_TZ).strftime("%Y-%m-%d %H:%M:%S")
started_at_gt = to_gt_str(detail.get("startedAt"))
updated_at_gt = to_gt_str(detail.get("updatedAt"))

# Optional: also keep your old “no text content” PDF list
text_empty_pdfs = []
for r in by_category.get("TEXT_EMPTY", []):
    for uri in extract_s3_uris(r):
        if uri.lower().endswith(".pdf"):
            text_empty_pdfs.append(uri)
text_empty_pdfs = dedupe_preserve_order(text_empty_pdfs)

# Write report
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write("BEDROCK KB INGESTION - LAST 10 JOBS + FAILURE REASONS\n")
    f.write("=====================================================\n\n")

    f.write(f"GeneratedAt GT : {generated_at_gt} (America/Guatemala)\n")
    f.write(f"KnowledgeBaseId: {KB_ID}\n")
    f.write(f"DataSourceId   : {DS_ID}\n\n")

    f.write("LAST 10 JOBS (newest -> oldest)\n")
    f.write("--------------------------------\n")
    for j in jobs10:
        jid = j.get("ingestionJobId")
        st = j.get("status")
        sa = to_gt_str(j.get("startedAt"))
        f.write(f"- {jid} | {st} | startedAt(GT): {sa}\n")

    f.write("\n--------------------------------\n")
    f.write("SELECTED JOB\n")
    f.write("--------------------------------\n")
    f.write(f"Selected       : {selected_reason}\n")
    f.write(f"IngestionJobId : {job_id}\n")
    f.write(f"Status         : {detail.get('status')}\n")
    f.write(f"StartedAt GT   : {started_at_gt}\n")
    f.write(f"UpdatedAt GT   : {updated_at_gt}\n")

    f.write("\n--------------------------------\n")
    f.write("SUMMARY BY CATEGORY\n")
    f.write("--------------------------------\n")
    total_reasons = sum(len(v) for v in by_category.values())
    f.write(f"Total failureReasons: {total_reasons}\n\n")

    cats_sorted = sorted(by_category.items(), key=lambda kv: len(kv[1]), reverse=True)
    for cat, arr in cats_sorted:
        f.write(f"- {cat}: {len(arr)}\n")

    f.write("\n--------------------------------\n")
    f.write("DETAIL (per category)\n")
    f.write("--------------------------------\n\n")
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

    f.write("\n================================\n")
    f.write("EXTRA: PDFs with TEXT_EMPTY (no text content)\n")
    f.write("================================\n")
    f.write(f"TOTAL: {len(text_empty_pdfs)}\n")
    for u in text_empty_pdfs:
        f.write(f"- {u}\n")

print(f"✔ Report written to {OUTPUT_FILE} "
      f"[selected job: {job_id}] "
      f"[reasons: {sum(len(v) for v in by_category.values())}] "
      f"[Guatemala time]")
