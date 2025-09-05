from flask import Flask, request, jsonify
from faster_whisper import WhisperModel
import subprocess
import os
from pathlib import Path

app = Flask(__name__)

MODEL_SIZE = "small"
DEVICE = "cpu"
COMPUTE_TYPE = "int8"

@app.route('/transcribir', methods=['POST'])
def transcribir_audio():
    data = request.get_json()

    if not data or "input_path" not in data:
        return jsonify({"error": "Se requiere el campo 'input_path'"}), 400

    input_path = data["input_path"]

    if not os.path.isfile(input_path):
        return jsonify({"error": f"El archivo no existe: {input_path}"}), 404

    try:
        # Extraer carpeta y nombre base
        base_path = Path(input_path)
        nombre_base = base_path.stem
        output_dir = base_path.parent

        # Definir rutas de salida en la misma carpeta
        audio_path = output_dir / f"{nombre_base}.wav"
        output_txt_path = output_dir / f"{nombre_base}.txt"

        # 1. Extraer audio del video con ffmpeg
        subprocess.run([
            "ffmpeg", "-i", str(input_path), "-vn",
            "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(audio_path), "-y"
        ], check=True)

        # 2. Cargar modelo Whisper
        model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)

        # 3. Transcribir (detección automática de idioma)
        segments, info = model.transcribe(str(audio_path), language=None, beam_size=1)

        # 4. Guardar texto plano
        with open(output_txt_path, "w", encoding="utf-8") as f:
            for seg in segments:
                f.write(f"{seg.text.strip()}\n")

        return jsonify({
            "message": "✅ Transcripción exitosa",
            "output_dir": str(output_dir),
            "audio_path": str(audio_path),
            "text_path": str(output_txt_path),
            "idioma_detectado": info.language
        })

    except subprocess.CalledProcessError as e:
        return jsonify({
            "error": "Error al extraer audio con ffmpeg",
            "stderr": e.stderr
        }), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, threaded=True)
