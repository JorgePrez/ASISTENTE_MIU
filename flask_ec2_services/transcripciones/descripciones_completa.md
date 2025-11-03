# 🎙️ Servicio de Transcripción de Video a Texto (Flask + Faster-Whisper + FFmpeg) — Amazon Linux 2023 (ARM / Graviton)

Este documento describe cómo instalar y configurar un microservicio **Flask** que:
1) extrae el audio de un video `.mp4` con **FFmpeg**,
2) transcribe el audio con **Faster-Whisper**,
3) guarda el resultado `.txt` en la misma carpeta del video,
4) expone un endpoint HTTP para uso automatizado.


---

## 🧰 Requisitos previos

- Servidor **Amazon Linux 2023** en **ARM (Graviton)**.
- Acceso SSH como usuario con permisos `sudo`.
- FFmpeg instalado (binario ARM64).
- Python 3 del sistema (invocado como `python3`) con `pip`.
- Carpetas de trabajo:
  - `/home/ec2-user/n8n_files/uploads` 

---

## 📁 1. Estructura de carpetas

```bash
sudo mkdir -p /home/ec2-user/n8n_files/uploads
sudo chown -R ec2-user:ec2-user /home/ec2-user/n8n_files
ls -l /home/ec2-user/n8n_files
```

Salida esperada:
```
drwxr-xr-x  uploads
```

> Los archivos `.wav` y `.txt` generados quedarán junto al `.mp4` en `uploads/`.

---

## 🎬 2. Instalar FFmpeg (ARM64 (gravitron estático))

> Amazon Linux 2023 no trae FFmpeg en repos por defecto. Usaremos binario estático para **ARM64**.

```bash
cd /usr/local/bin
sudo curl -L -o ffmpeg.tar.xz https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz
sudo tar -xf ffmpeg.tar.xz
cd ffmpeg-*-static
sudo cp ffmpeg /usr/local/bin/
sudo chmod +x /usr/local/bin/ffmpeg
ffmpeg -version
```

Debes ver una versión similar a:
```
ffmpeg version 7.x static ... (arm64)
```

---

##  Instalar dependencias Python

```bash
sudo dnf install -y python3-pip
sudo python3 -m pip install --upgrade pip
sudo python3 -m pip install flask faster-whisper ffmpeg-python
```

Validación rápida:
```bash
python3 -c "import flask, faster_whisper; print('OK Flask + Faster-Whisper')"
```

---

## Crear el microservicio Flask `/root/api_transcripcion.py`

```bash
sudo nano /root/api_transcripcion.py
```

Pega el contenido **completo**:

```python
from flask import Flask, request, jsonify
from faster_whisper import WhisperModel
import subprocess
import os
from pathlib import Path

app = Flask(__name__)

# Configuración del modelo
MODEL_SIZE = "small"    # opciones útiles: tiny, base, small, medium
DEVICE = "cpu"          # en Graviton/ARM sin GPU usamos CPU
COMPUTE_TYPE = "int8"   # int8 reduce RAM/CPU; también: float16, int8_float16, etc.

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

        # Rutas de salida
        audio_path = output_dir / f"{nombre_base}.wav"
        output_txt_path = output_dir / f"{nombre_base}.txt"

        # 1) Extraer audio mono 16kHz con FFmpeg
        subprocess.run([
            "ffmpeg", "-i", str(input_path), "-vn",
            "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(audio_path), "-y"
        ], check=True)

        # 2) Cargar modelo Whisper optimizado
        model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)

        # 3) Transcribir (detección automática de idioma)
        segments, info = model.transcribe(str(audio_path), language=None, beam_size=1)

        # 4) Guardar texto plano
        with open(output_txt_path, "w", encoding="utf-8") as f:
            f.write(f"Transcripción del vídeo: {nombre_base}\n\n")
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
            "stderr": getattr(e, 'stderr', 'N/A')
        }), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    # Puerto por defecto de este servicio
    app.run(host='0.0.0.0', port=5002, threaded=True)
```

Permisos (opcional):
```bash
sudo chown root:root /root/api_transcripcion.py
sudo chmod 644 /root/api_transcripcion.py
```

---

##  Prueba manual (antes del servicio systemd)

Deja corriendo el servidor Flask manualmente:
```bash
sudo python3 /root/api_transcripcion.py
```

En otra terminal, coloca un video de prueba en `uploads/` y haz la llamada:

```bash
# ejemplo: mover un video a uploads
# (copia o genera tu mp4 en la carpeta)
ls -lh /home/ec2-user/n8n_files/uploads

# llamada al endpoint:
curl -X POST http://localhost:5002/transcribir \
  -H "Content-Type: application/json" \
  -d '{"input_path": "/home/ec2-user/n8n_files/uploads/mi_video.mp4"}'
```

Salida esperada:
```json
{
  "message": "✅ Transcripción exitosa",
  "output_dir": "/home/ec2-user/n8n_files/uploads",
  "audio_path": "/home/ec2-user/n8n_files/uploads/mi_video.wav",
  "text_path": "/home/ec2-user/n8n_files/uploads/mi_video.txt",
  "idioma_detectado": "es"
}
```

Verifica archivos generados:
```bash
ls -lh /home/ec2-user/n8n_files/uploads
```

---

## 🔧 6. Crear el servicio systemd `flasktranscribe.service`

```bash
sudo nano /etc/systemd/system/flasktranscribe.service
```

Contenido literal:
```ini
[Unit]
Description=Servidor Flask para transcripción con faster-whisper
After=network.target

[Service]
User=root
WorkingDirectory=/root
ExecStart=/usr/bin/python3 /root/api_transcripcion.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Activar y arrancar:
```bash
sudo systemctl daemon-reload
sudo systemctl enable flasktranscribe.service
sudo systemctl start flasktranscribe.service
sudo systemctl status flasktranscribe.service
```

Logs en vivo:
```bash
sudo journalctl -u flasktranscribe.service -f
```

---

##  Probar el endpoint con el servicio activo

```bash
curl -X POST http://localhost:5002/transcribir \
  -H "Content-Type: application/json" \
  -d '{"input_path": "/home/ec2-user/n8n_files/uploads/mi_video.mp4"}'
```

Verificar `.wav` y `.txt` en `uploads/`.

---


##  Limpieza nocturna 

Se utiliza el mismo cron usado para borrar los resultados de libreoffice 

---

## Al realizar cambios

- Reiniciar el servicio tras cambios en el `.py`:
  ```bash
  sudo systemctl restart flasktranscribe.service
  ```
- Ver estado:
  ```bash
  sudo systemctl status flasktranscribe.service
  ```
- Ver logs:
  ```bash
  sudo journalctl -u flasktranscribe.service -f
  ```

---

## Ajustes de modelo y rendimiento

- `MODEL_SIZE`: `tiny`, `base`, `small`, `medium` (a mayor tamaño, mayor precisión y consumo).
- `DEVICE="cpu"` para Graviton sin GPU.
- `COMPUTE_TYPE`: `int8` (ahorra RAM/CPU), `float16` (más precisión si hay soporte), `int8_float16` (mix).

Ejemplo para más velocidad en CPU con menos RAM:
```python
MODEL_SIZE = "tiny"
COMPUTE_TYPE = "int8"
```

---


## ✅ Estado final esperado

| Elemento | Estado |
|---|---|
| FFmpeg (ARM64) instalado | ✅ |
| Dependencias Python (Flask, Faster-Whisper) | ✅ |
| Script `/root/api_transcripcion.py` | ✅ |
| Servicio `flasktranscribe.service` activo | ✅ |
| Transcripción con `curl` funcionando | ✅ |

---
