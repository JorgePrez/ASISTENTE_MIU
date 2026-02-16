import csv
import json
import boto3
from botocore.exceptions import ClientError
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuración
BUCKET_BDA = "miu-documentos-bedrock-procesing"
AWS_REGION = 'us-west-2'

# Cliente S3
s3 = boto3.client('s3', region_name=AWS_REGION)

def parse_s3_path(path):
    """Convierte PATH_ADUNTO a bucket y key"""
    # Si es URL completa (https://bucket.s3.region.amazonaws.com/key)
    if path.startswith('https://'):
        # Extraer bucket del hostname
        parts = path.replace('https://', '').split('/')
        if len(parts) >= 2:
            hostname = parts[0]
            # bucket.s3.region.amazonaws.com -> bucket
            bucket = hostname.split('.')[0]
            key = '/'.join(parts[1:])
            return bucket, key
    
    # Si es formato s3://bucket/key
    elif path.startswith('s3://'):
        path = path[5:]  # Remover s3://
        parts = path.split('/', 1)
        if len(parts) == 2:
            return parts[0], parts[1]
    
    # Si es formato /bucket/key o bucket/key
    else:
        path = path.strip('/')
        parts = path.split('/', 1)
        if len(parts) == 2:
            return parts[0], parts[1]
    
    return None, None

def check_metadata_exists(bucket, key):
    """Verifica si existe metadata.json en origen"""
    try:
        s3.head_object(Bucket=bucket, Key=key + '.metadata.json')
        return True
    except ClientError:
        return False

def check_pdf_not_in_bda(key):
    """Verifica que PDF NO existe en bucket BDA"""
    try:
        s3.head_object(Bucket=BUCKET_BDA, Key=key)
        return False  # Si existe, no cumple condición
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code in ['404', 'NotFound', 'NoSuchKey']:
            return True  # No existe, cumple condición
        return False  # Otro error

def process_document(row):
    """Procesa un documento y verifica condiciones"""
    miu_doc = row['MIU_DOCUMENTOS']
    path = row['PATH_ADUNTO']
    
    bucket, key = parse_s3_path(path)
    if not bucket or not key:
        return None
    
    # Paso 4: metadata debe existir en origen
    if not check_metadata_exists(bucket, key):
        return None
    
    # Paso 5: PDF no debe existir en BDA
    if not check_pdf_not_in_bda(key):
        return None
    
    # Si cumple ambas condiciones
    return {
        'miu_documentos': miu_doc,
        'src': f'/{bucket}/{key}',
        'src_meta': f'/{bucket}/{key}.metadata.json',
        'dst': f'/{BUCKET_BDA}/{key}',
        'dst_meta': f'/{BUCKET_BDA}/{key}.metadata.json'
    }

def main():
    # Leer CSV
    documents = []
    with open('pinecone_results_not_found.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        documents = list(reader)
    
    # Procesar documentos en paralelo
    valid_items = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(process_document, doc): doc for doc in documents}
        
        for future in as_completed(futures):
            result = future.result()
            if result:
                valid_items.append(result)
    
    # Generar CSV de totales
    with open('bedrock_validation_totals.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['CATEGORIA', 'TOTAL'])
        writer.writerow(['DOCUMENTOS', len(documents)])
        writer.writerow(['CUMPLEN_CONDICIONES PARA PROCESAMIENTO', len(valid_items)])
        writer.writerow(['NO_CUMPLEN_CONDICIONES', len(documents) - len(valid_items)])
    
    # Generar JSON con rutas
    result_json = {
        'total': len(valid_items),
        'items': [
            {
                'src': item['src'],
                'src_meta': item['src_meta'],
                'dst': item['dst'],
                'dst_meta': item['dst_meta']
            }
            for item in valid_items
        ]
    }
    
    with open('bedrock_validation_routes.json', 'w', encoding='utf-8') as f:
        json.dump(result_json, f, indent=2, ensure_ascii=False)
    
    print(f"Documentos: {len(documents)}")
    print(f"Cumplen condiciones para procesamiento: {len(valid_items)}")
    print("Archivos generados: bedrock_validation_totals.csv y bedrock_validation_routes.json")

if __name__ == "__main__":
    main()
