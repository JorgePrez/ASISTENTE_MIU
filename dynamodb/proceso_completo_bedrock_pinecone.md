# Proceso Completo: Análisis Pinecone y Migración Bedrock

## Resumen del Proceso
Este documento describe el proceso completo realizado para analizar documentos en Pinecone, identificar cuáles no han sido procesados, y preparar su migración a Bedrock Data Automation para reprocesamiento.

## 1. Análisis Inicial de Pinecone

### Script Base: `script_pinecone_filtro_pdf.py`
- **Propósito**: Script original que obtiene documentos desde API y verifica su existencia en Pinecone
- **Funcionalidad**: 
  - Consulta API: `https://miu.ufm.edu/asistente_documentos_api.php`
  - Verifica existencia en Pinecone usando filtro `miu_documentos`
  - Retorna solo documentos NO encontrados en formato JSON

## 2. Generación de Reportes CSV

### Script Modificado: `script_pinecone_csv_results.py`
- **Basado en**: `script_pinecone_filtro_pdf.py`
- **Mejoras implementadas**:
  - Escritura fila por fila con `flush()` para procesamiento en tiempo real
  - Cambio de orden de columnas: `MIU_DOCUMENTOS`, `ENCONTRADO_EN_PINECONE`, `PATH_ADUNTO`
  - Generación de múltiples archivos CSV

### Archivos de Salida Generados:
1. **`pinecone_results_found.csv`**
   - Documentos que SÍ existen en Pinecone
   - Columnas: `MIU_DOCUMENTOS`, `PATH_ADUNTO`

2. **`pinecone_results_not_found.csv`**
   - Documentos que NO existen en Pinecone
   - Columnas: `MIU_DOCUMENTOS`, `PATH_ADUNTO`

3. **`pinecone_results_totals.csv`**
   - Resumen estadístico completo
   - Columnas: `CATEGORIA`, `TOTAL`
   - Filas: `ENCONTRADOS`, `NO_ENCONTRADOS`, `TOTAL_PROCESADOS`

4. **`pinecone_results_no_procesados.csv`**
   - Solo el total de documentos no procesados
   - Columnas: `NO_PROCESADOS`
   - Una fila con el número total

## 3. Análisis del Script PHP Bedrock

### Script Analizado: `pinecone_bedrock_invoque.php`
- **Propósito**: Identifica PDFs que fallaron en Bedrock Knowledge Base
- **Proceso**:
  1. Obtiene último job de ingestion de Bedrock
  2. Analiza `failureReasons` buscando "no text content found"
  3. Extrae URIs S3 de PDFs fallidos
  4. **Validación 4**: Verifica existencia de metadata en bucket origen
  5. **Validación 5**: Confirma que PDF NO existe en bucket destino
  6. Genera rutas en formato n8n para copiar archivos

## 4. Validación de Documentos para Bedrock

### Script: `bedrock_validation.py`
- **Input**: `pinecone_results_not_found.csv`
- **Proceso**: Aplica validaciones 4 y 5 del script PHP
- **Validaciones**:
  - **Paso 4**: Metadata existe en bucket origen (`archivo.pdf.metadata.json`)
  - **Paso 5**: PDF NO existe en bucket destino (`miu-documentos-bedrock-procesing`)
- **Procesamiento**: Paralelo con ThreadPoolExecutor (10 workers)

### Archivos de Salida:
1. **`bedrock_validation_totals.csv`**
   ```csv
   CATEGORIA,TOTAL
   DOCUMENTOS_PROCESADOS,X
   CUMPLEN_CONDICIONES,Y
   NO_CUMPLEN_CONDICIONES,Z
   ```

2. **`bedrock_validation_routes.json`**
   ```json
   {
     "total": Y,
     "items": [
       {
         "src": "/bucket-origen/archivo.pdf",
         "src_meta": "/bucket-origen/archivo.pdf.metadata.json",
         "dst": "/miu-documentos-bedrock-procesing/archivo.pdf",
         "dst_meta": "/miu-documentos-bedrock-procesing/archivo.pdf.metadata.json"
       }
     ]
   }
   ```

## 5. Ejecución de Copias S3

### Script: `bedrock_validation2.py`
- **Input**: `bedrock_validation_routes.json`
- **Configuración**:
  - `EXECUTE_COPY = False`: Modo simulación (default)
  - `MAX_ITEMS = 10`: Límite para pruebas
- **Proceso**:
  - Lee rutas del JSON
  - Copia PDF: `src` → `dst`
  - Copia metadata: `src_meta` → `dst_meta`
  - Manejo de errores sin detener procesamiento

### Archivo de Salida:
- **`bedrock_copy_errors.csv`**
  ```csv
  SRC_PATH,DST_PATH,ERROR_TYPE,ERROR_MESSAGE
  ```

## 6. Estimación de Tiempos Bedrock

### Escenario: 384 libros escaneados de economía
- **Procesamiento**: Bedrock Data Automation (BDA) maneja OCR automáticamente
- **Tiempo estimado**: 12-16 horas
- **Factores**:
  - Libros de 200-500+ páginas
  - Texto denso con terminología técnica
  - Gráficos, tablas, ecuaciones
  - Calidad variable de escaneo

## Flujo Completo del Proceso

```
1. script_pinecone_filtro_pdf.py (base)
   ↓
2. script_pinecone_csv_results.py
   ↓ genera
3. pinecone_results_not_found.csv
   ↓ input para
4. bedrock_validation.py
   ↓ genera
5. bedrock_validation_routes.json
   ↓ input para
6. bedrock_validation2.py
   ↓ ejecuta S3
7. Documentos listos para Bedrock BDA
```

## Archivos Finales Generados

### CSVs de Análisis:
- `pinecone_results_found.csv`
- `pinecone_results_not_found.csv`
- `pinecone_results_totals.csv`
- `pinecone_results_no_procesados.csv`
- `bedrock_validation_totals.csv`
- `bedrock_copy_errors.csv`

### JSON de Configuración:
- `bedrock_validation_routes.json`

### Scripts Desarrollados:
- `script_pinecone_csv_results.py`
- `bedrock_validation.py`
- `bedrock_validation2.py`

## Resultado Final
Sistema completo para identificar documentos no procesados en Pinecone y migrarlos automáticamente a Bedrock Data Automation para reprocesamiento con OCR mejorado.
