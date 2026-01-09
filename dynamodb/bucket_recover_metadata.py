import pandas as pd
import os

INPUT_CSV = "preview_restore.csv"              # el CSV recién creado por el restore
OUTPUT_CSV = "metadata_targets.csv"            # salida: qué metadata correspondería

def is_pdf(key: str) -> bool:
    return str(key).lower().endswith(".pdf")

def build_metadata_key(original_key: str) -> str:
    """
    Regla: <key_original>.metadata.json
    Ej: .../archivo.pdf  ->  .../archivo.pdf.metadata.json
    """
    return f"{original_key}.metadata.json"

def build_s3_path(bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key}"

def main():
    df = pd.read_csv(INPUT_CSV)

    # Validación mínima (usamos bucket y key del preview_restore.csv)
    required = {"bucket", "key", "region"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Faltan columnas en {INPUT_CSV}: {missing}")

    # Solo principales PDF (si quieres incluir otros, quita este filtro)
    df_pdf = df[df["key"].astype(str).apply(is_pdf)].copy()

    # Construir metadata key y s3_path asociado
    df_pdf["metadata_key"] = df_pdf["key"].astype(str).apply(build_metadata_key)
    df_pdf["metadata_s3_path"] = df_pdf.apply(lambda r: build_s3_path(r["bucket"], r["metadata_key"]), axis=1)

    # (Opcional) conservar el original también para trazabilidad
    df_out = df_pdf[[
        "bucket", "region",
        "key", "s3_path" if "s3_path" in df_pdf.columns else "key",
        "metadata_key", "metadata_s3_path"
    ]].copy()

    # Si no existe s3_path en el CSV, lo generamos
    if "s3_path" not in df_pdf.columns:
        df_out["s3_path"] = df_out.apply(lambda r: build_s3_path(r["bucket"], r["key"]), axis=1)
        df_out = df_out[["bucket", "region", "key", "s3_path", "metadata_key", "metadata_s3_path"]]

    df_out.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")

    print("--- LISTO ---")
    print(f"Principales PDF leídos: {len(df_pdf)}")
    print(f"✅ Archivo generado: {OUTPUT_CSV}")

    # Muestra 5 ejemplos
    if not df_out.empty:
        print("\nEjemplos (5):")
        for _, r in df_out.head(5).iterrows():
            print(f"- Principal: {r['s3_path']}")
            print(f"  Metadata : {r['metadata_s3_path']}")

if __name__ == "__main__":
    main()
