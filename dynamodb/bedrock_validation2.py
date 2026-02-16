import json
import boto3
import csv
from botocore.exceptions import ClientError

# Configuración
AWS_REGION = 'us-west-2'
EXECUTE_COPY = True # Bandera para ejecutar copia real
MAX_ITEMS = 0  # Número máximo de elementos a procesar (para pruebas)

# Cliente S3
s3 = boto3.client('s3', region_name=AWS_REGION)

def parse_s3_path(path):
    """Convierte path formato /bucket/key a bucket y key"""
    path = path.strip('/')
    parts = path.split('/', 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return None, None

def copy_s3_object(src_path, dst_path, error_writer):
    """Copia objeto de src a dst"""
    src_bucket, src_key = parse_s3_path(src_path)
    dst_bucket, dst_key = parse_s3_path(dst_path)
    
    if not all([src_bucket, src_key, dst_bucket, dst_key]):
        error_msg = f"Rutas inválidas - src: {src_path}, dst: {dst_path}"
        error_writer.writerow([src_path, dst_path, "RUTA_INVALIDA", error_msg])
        return False
    
    if EXECUTE_COPY:
        try:
            copy_source = {'Bucket': src_bucket, 'Key': src_key}
            s3.copy_object(CopySource=copy_source, Bucket=dst_bucket, Key=dst_key)
            print(f"COPIADO: {src_path} -> {dst_path}")
            return True
        except ClientError as e:
            error_msg = str(e)
            error_writer.writerow([src_path, dst_path, "S3_ERROR", error_msg])
            return False
    else:
        print(f"SIMULACIÓN: {src_path} -> {dst_path}")
        return True

def main():
    # Leer JSON con rutas
    try:
        with open('bedrock_validation_routes.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("ERROR: No se encontró bedrock_validation_routes.json")
        return
    
    items = data.get('items', [])
    # Limitar número de elementos para prueba
    if MAX_ITEMS > 0:
        items = items[:MAX_ITEMS]
    total_items = len(items)
    successful_copies = 0
    
    print(f"Modo: {'EJECUCIÓN REAL' if EXECUTE_COPY else 'SIMULACIÓN'}")
    if MAX_ITEMS > 0:
        print(f"Procesando solo {MAX_ITEMS} elementos (modo prueba)")
    print(f"Total de elementos a procesar: {total_items}")
    print("-" * 50)
    
    # Abrir CSV para errores
    with open('bedrock_copy_errors.csv', 'w', newline='', encoding='utf-8') as error_file:
        error_writer = csv.writer(error_file)
        error_writer.writerow(['SRC_PATH', 'DST_PATH', 'ERROR_TYPE', 'ERROR_MESSAGE'])
        
        for i, item in enumerate(items, 1):
            print(f"\n[{i}/{total_items}]")
            
            # Copiar archivo PDF
            pdf_success = copy_s3_object(item['src'], item['dst'], error_writer)
            
            # Copiar metadata
            meta_success = copy_s3_object(item['src_meta'], item['dst_meta'], error_writer)
            
            if pdf_success and meta_success:
                successful_copies += 1
            
            error_file.flush()  # Escribir errores inmediatamente

    #total_items = 173
    #successful_copies = 173

    print("\n" + "=" * 50)
    print(f"Resumen:")
    print(f"Total procesados: {total_items}")
    print(f"Exitosos: {successful_copies}")
    print(f"Fallidos: {total_items - successful_copies}")
    print(f"Errores guardados en: bedrock_copy_errors.csv")
    
    if not EXECUTE_COPY:
        print("\nPara ejecutar las copias reales, cambiar EXECUTE_COPY = True")

if __name__ == "__main__":
    main()
