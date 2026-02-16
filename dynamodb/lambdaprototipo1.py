import json
import time
import boto3
from urllib.parse import urlparse

bedrock = boto3.client("bedrock-data-automation", region_name="us-west-2")
s3 = boto3.client("s3")

POLL_SECONDS = 5
MAX_WAIT = 300  # 5 minutos

def parse_s3_uri(uri: str):
    parsed = urlparse(uri)
    return parsed.netloc, parsed.path.lstrip("/")

def lambda_handler(event, context):
    """
    event = {
        "s3_uri": "s3://mi-bucket/docs/ejemplo.pdf"
    }
    """

    s3_uri = event.get("s3_uri")
    if not s3_uri:
        return {"status": "error", "message": "s3_uri requerido"}

    bucket, key = parse_s3_uri(s3_uri)

    base_prefix = key.rsplit("/", 1)[0]
    filename = key.split("/")[-1].rsplit(".", 1)[0]

    # Output temporal de BDA
    output_prefix = f"{base_prefix}/__bda_output/{filename}/"

    # 1️⃣ Invocar Data Automation (async)
    response = bedrock.invoke_data_automation_async(
        inputConfiguration={
            "s3Uri": f"s3://{bucket}/{key}"
        },
        outputConfiguration={
            "s3Uri": f"s3://{bucket}/{output_prefix}"
        }
    )

    job_id = response["jobId"]

    # 2️⃣ Esperar a que termine
    waited = 0
    status = "IN_PROGRESS"

    while status == "IN_PROGRESS" and waited < MAX_WAIT:
        time.sleep(POLL_SECONDS)
        waited += POLL_SECONDS

        job = bedrock.get_data_automation_status(jobId=job_id)
        status = job["status"]

        if status == "FAILED":
            return {
                "status": "error",
                "message": "Data Automation falló",
                "details": job
            }

    if status != "COMPLETED":
        return {
            "status": "error",
            "message": "Timeout esperando Data Automation"
        }

    # 3️⃣ Leer output JSON generado
    objects = s3.list_objects_v2(
        Bucket=bucket,
        Prefix=output_prefix
    ).get("Contents", [])

    extracted_text = []

    for obj in objects:
        if obj["Key"].endswith(".json"):
            data = s3.get_object(Bucket=bucket, Key=obj["Key"])
            payload = json.loads(data["Body"].read())

            # Extraer texto (estructura típica de BDA)
            for page in payload.get("pages", []):
                extracted_text.append(page.get("text", ""))

    final_text = "\n\n".join(extracted_text).strip()

    if not final_text:
        final_text = "[Sin texto extraíble]"

    # 4️⃣ Guardar .txt en la misma ruta del PDF
    txt_key = f"{base_prefix}/{filename}.txt"

    s3.put_object(
        Bucket=bucket,
        Key=txt_key,
        Body=final_text.encode("utf-8"),
        ContentType="text/plain; charset=utf-8"
    )

    return {
        "status": "ok",
        "pdf": s3_uri,
        "txt": f"s3://{bucket}/{txt_key}",
        "pages_extracted": len(extracted_text)
    }
