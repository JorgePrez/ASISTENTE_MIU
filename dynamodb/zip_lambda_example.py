import os
import re
import json
import urllib.parse
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import boto3
import zipfile
from botocore.exceptions import ClientError

s3 = boto3.client("s3")

# Defaults / Limits
DEFAULT_MAX_FILES = int(os.getenv("MAX_FILES", "500"))
DEFAULT_MAX_OUT_BYTES = int(os.getenv("MAX_OUT_BYTES", str(2_000_000_000)))  # 2GB

IGNORE_BASENAMES = {".ds_store", "thumbs.db"}
IGNORE_PREFIXES = ("__MACOSX/",)


@dataclass
class InputParams:
    bucket: str
    key: str
    max_files: int = DEFAULT_MAX_FILES
    max_out_bytes: int = DEFAULT_MAX_OUT_BYTES


def _parse_s3_location(event: Dict) -> Tuple[str, str]:
    """
    Accepts:
      - event["s3_url"] = "https://bucket.s3.region.amazonaws.com/key..."
      - event["s3_url"] = "s3://bucket/key..."
      - event["bucket"] + event["key"]
    Returns (bucket, key)
    """
    if "bucket" in event and "key" in event and event["bucket"] and event["key"]:
        return event["bucket"], event["key"]

    s3_url = event.get("s3_url") or event.get("s3_path") or event.get("url")
    if not s3_url:
        raise ValueError("Missing input. Provide {bucket,key} or {s3_url}.")

    s3_url = str(s3_url).strip()

    # s3://bucket/key
    if s3_url.lower().startswith("s3://"):
        parts = urllib.parse.urlparse(s3_url)
        bucket = parts.netloc
        key = parts.path.lstrip("/")
        if not bucket or not key:
            raise ValueError(f"Invalid s3 url: {s3_url}")
        return bucket, key

    # https://bucket.s3.region.amazonaws.com/key...
    if s3_url.lower().startswith("http://") or s3_url.lower().startswith("https://"):
        parts = urllib.parse.urlparse(s3_url)
        host = parts.netloc
        path = parts.path.lstrip("/")

        m = re.match(
            r"^([a-z0-9\.\-]+)\.s3[.\-][a-z0-9\-]+\.amazonaws\.com$",
            host,
            re.IGNORECASE
        )
        if m:
            bucket = m.group(1)
            key = urllib.parse.unquote(path)
            return bucket, key

        if host.lower().startswith("s3.amazonaws.com"):
            pieces = path.split("/", 1)
            if len(pieces) != 2:
                raise ValueError(f"Invalid path-style S3 URL: {s3_url}")
            bucket = pieces[0]
            key = urllib.parse.unquote(pieces[1])
            return bucket, key

        raise ValueError(f"Unrecognized S3 URL format: {s3_url}")

    raise ValueError(f"Unrecognized input format: {s3_url}")


def _safe_relpath(name: str) -> Optional[str]:
    """
    Returns a safe relative path for an entry, or None if it should be ignored/rejected.
    Blocks:
      - absolute paths
      - path traversal (..)
      - windows backslashes
      - directories
      - obvious junk
    """
    if not name:
        return None

    n = name.replace("\\", "/").strip()
    if n.endswith("/"):
        return None

    for pref in IGNORE_PREFIXES:
        if n.startswith(pref):
            return None

    base = n.split("/")[-1].lower()
    if base in IGNORE_BASENAMES:
        return None

    if n.startswith("/") or n.startswith("\\"):
        return None

    parts = n.split("/")
    if any(p == ".." for p in parts):
        return None

    n = re.sub(r"/{2,}", "/", n)

    if any(ord(c) < 32 for c in n):
        return None

    return n


def _derive_dest_prefix(zip_key: str) -> str:
    """
    If zip_key = DATA-DOCS/.../materiales.zip
    dest_prefix = DATA-DOCS/.../materiales/
    """
    if "/" in zip_key:
        base_prefix = zip_key.rsplit("/", 1)[0] + "/"
        filename = zip_key.rsplit("/", 1)[1]
    else:
        base_prefix = ""
        filename = zip_key

    folder = filename
    if folder.lower().endswith(".zip"):
        folder = folder[:-4]

    return f"{base_prefix}{folder}/"


def lambda_handler(event, context):
    """
    Input:
      { "s3_url": "https://miu-documentos.s3.us-west-2.amazonaws.com/DATA-DOCS/.../file.zip" }
      or { "bucket": "miu-documentos", "key": "DATA-DOCS/.../file.zip" }

    Output:
      { "ok": true, "bucket": "...", "zip_key": "...", "dest_prefix": ".../", "extracted_count": N, ... }
      BUT (important): only dest_prefix is needed by n8n; n8n will list objects under that prefix.
    """
    try:
        event = event if isinstance(event, dict) else {}
        bucket, key = _parse_s3_location(event)

        params = InputParams(
            bucket=bucket,
            key=key,
            max_files=int(event.get("max_files", DEFAULT_MAX_FILES)),
            max_out_bytes=int(event.get("max_out_bytes", DEFAULT_MAX_OUT_BYTES)),
        )

        if not params.key.lower().endswith(".zip"):
            raise ValueError(f"Key is not a .zip: {params.key}")

        dest_prefix = _derive_dest_prefix(params.key)

        # Download zip to /tmp (zipfile needs seek)
        local_zip = "/tmp/input.zip"
        s3.download_file(params.bucket, params.key, local_zip)

        extracted_count = 0
        skipped_count = 0
        errors_count = 0
        total_out_bytes = 0

        with zipfile.ZipFile(local_zip, "r") as zf:
            infos = zf.infolist()

            if len(infos) > params.max_files:
                raise RuntimeError(f"Too many files in zip: {len(infos)} > max_files={params.max_files}")

            for info in infos:
                safe_name = _safe_relpath(info.filename)
                if safe_name is None:
                    skipped_count += 1
                    continue

                file_size = int(getattr(info, "file_size", 0) or 0)
                if total_out_bytes + file_size > params.max_out_bytes:
                    raise RuntimeError(
                        f"Uncompressed output would exceed limit: {total_out_bytes + file_size} > max_out_bytes={params.max_out_bytes}"
                    )

                out_key = f"{dest_prefix}{safe_name}"

                try:
                    with zf.open(info, "r") as src_fp:
                        s3.upload_fileobj(src_fp, params.bucket, out_key)

                    extracted_count += 1
                    total_out_bytes += file_size

                except Exception:
                    errors_count += 1
                    continue

        return {
            "ok": True,
            "bucket": params.bucket,
            "zip_key": params.key,
            "dest_prefix": dest_prefix,  # <-- esto es lo principal para n8n
            "extracted_count": extracted_count,
            "skipped_count": skipped_count,
            "errors_count": errors_count,
            "total_out_bytes": total_out_bytes,
        }

    except ClientError as e:
        return {"ok": False, "error": f"AWS ClientError: {str(e)}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
