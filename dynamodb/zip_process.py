import boto3
from statistics import mean

# =========================
# Configuración
# =========================
BUCKET_NAME = "miu-documentos"   # ajusta si aplica
PREFIX = "DATA-DOCS/miu-hml/documentos/"                      # ej: "DATA-DOCS/miu-hml/documentos/"
REGION = "us-west-2"

# =========================
# Cliente S3
# =========================
s3 = boto3.client("s3", region_name=REGION)

# =========================
# Recolección de tamaños
# =========================
zip_sizes = []

paginator = s3.get_paginator("list_objects_v2")
pages = paginator.paginate(
    Bucket=BUCKET_NAME,
    Prefix=PREFIX
)

for page in pages:
    for obj in page.get("Contents", []):
        key = obj["Key"]
        if key.lower().endswith(".zip"):
            zip_sizes.append(obj["Size"])

# =========================
# Resultados
# =========================
if not zip_sizes:
    print("No se encontraron archivos .zip")
else:
    total_zips = len(zip_sizes)
    total_size = sum(zip_sizes)

    print("===== ZIPs en S3 =====")
    print(f"Cantidad total : {total_zips}")
    print(f"Tamaño total   : {total_size / (1024**2):.2f} MB")
    print(f"Tamaño promedio: {mean(zip_sizes) / (1024**2):.2f} MB")
    print(f"Tamaño mínimo  : {min(zip_sizes) / (1024**2):.2f} MB")
    print(f"Tamaño máximo  : {max(zip_sizes) / (1024**2):.2f} MB")
