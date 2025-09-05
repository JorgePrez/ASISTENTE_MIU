from flask import Flask, request, jsonify
import subprocess
import os
from pathlib import Path

app = Flask(__name__)

SOFFICE_BIN = "/opt/libreoffice25.8/program/soffice"
OUTPUT_DIR = "/home/ec2-user/n8n_files/conversions"

@app.route('/convert', methods=['POST'])
def convert_file():
    data = request.get_json()

    if not data or "input_path" not in data or "output_format" not in data:
        return jsonify({
            "error": "Se requieren los campos 'input_path' y 'output_format'"
        }), 400

    input_path = data["input_path"]
    output_format = data["output_format"].lower()

    if not os.path.isfile(input_path):
        return jsonify({"error": f"El archivo no existe: {input_path}"}), 404

    try:
        # Ejecutar comando con formato deseado
        cmd = [
            SOFFICE_BIN,
            "--headless",
            "--convert-to", output_format,
            "--outdir", OUTPUT_DIR,
            input_path
        ]

        process = subprocess.run(cmd, capture_output=True, text=True)

        if process.returncode != 0:
            return jsonify({
                "error": "Fallo en la conversión",
                "stderr": process.stderr
            }), 500

        nombre_base = Path(input_path).stem
        nombre_salida = f"{nombre_base}.{output_format}"
        ruta_salida = os.path.join(OUTPUT_DIR, nombre_salida)

        return jsonify({
            "message": f"Conversión a {output_format} exitosa",
            "output_path": ruta_salida
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, threaded=True)
