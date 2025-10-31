# 📌 Asistente MIU – Despliegue en servidor EC2 (Streamlit + Systemd)

Este documento describe el proceso para ejecutar el chatbot **Asistente MIU** como un servicio en Linux, usando **Python 3.11**, **Streamlit** y **systemd**, de manera que la aplicación se ejecute automáticamente en segundo plano y se reinicie si falla.

---

## 📁 Estructura del proyecto

/home/ec2-user/ASISTENTE_MIU
│── asistente_miu.py
│── config/
│── dynamodb/
│── start_streamlit_miu.sh   ← Script de arranque

---

## ✅ Requisitos previos

- Python 3.11 instalado (`python3.11 --version`)
- Streamlit instalado en esa versión (`pip3.11 install streamlit`)
- Usuario que ejecuta el servicio: ec2-user

---

## 🚀 Paso 1 – Crear script de ejecución

sudo nano /home/ec2-user/start_streamlit_miu.sh

Contenido:

#!/bin/bash
cd /home/ec2-user/ASISTENTE_MIU
/usr/local/bin/python3.11 -m streamlit run asistente_miu.py --server.port 8191

Guardar y salir (`CTRL + O`, `ENTER`, `CTRL + X`).

Dar permisos de ejecución:

sudo chmod +x /home/ec2-user/start_streamlit_miu.sh

---

## 🔧 Paso 2 – Crear servicio systemd

sudo nano /etc/systemd/system/streamlit_miu.service

Contenido:

[Unit]
Description=Asistente MIU - Streamlit
After=network.target

[Service]
ExecStart=/home/ec2-user/start_streamlit_miu.sh
Restart=always
RestartSec=3
User=ec2-user
WorkingDirectory=/home/ec2-user/ASISTENTE_MIU

[Install]
WantedBy=multi-user.target

Guardar y salir (`CTRL + O`, `ENTER`, `CTRL + X`).

---

## ▶️ Paso 3 – Activar el servicio

sudo systemctl daemon-reload
sudo systemctl enable streamlit_miu.service
sudo systemctl start streamlit_miu.service
sudo systemctl status streamlit_miu.service

Salida esperada:

Active: active (running)

---

## 🧪 Ejecución manual (opcional)

python3.11 -m streamlit run asistente_miu.py --server.port 8191

---

## 🛠️ Comandos útiles

| Acción                   | Comando                                      |
|--------------------------|----------------------------------------------|
| Ver estado               | sudo systemctl status streamlit_miu.service |
| Reiniciar servicio       | sudo systemctl restart streamlit_miu.service |
| Detener servicio         | sudo systemctl stop streamlit_miu.service    |
| Ver logs en tiempo real  | sudo journalctl -u streamlit_miu.service -f  |

---

## 🌐 Acceso local

http://<IP-del-servidor>:8191

---

## 📝 Notas finales

- El servicio se ejecuta automáticamente al iniciar el servidor.
- Si el archivo `asistente_miu.py` cambia, solo necesitas reiniciar el servicio:
  sudo systemctl restart streamlit_miu.service
- No se requiere `screen`, `tmux` ni dejar la terminal abierta.

---

## 🌍 Acceso público temporal con Ngrok (dominio fijo)

El asistente MIU está expuesto a internet mediante **Ngrok**, usando un dominio reservado y un servicio `systemd` que se inicia automáticamente con el servidor.

### 🔐 Dominio público

https://usefully-tops-cattle.ngrok-free.app


*(Útil mientras no exista dominio oficial o DNS propio)*

### ⚙️ Servicio `systemd` de Ngrok

El túnel se gestiona con un servicio llamado `ngrok.service`, el cual:

- Se ejecuta automáticamente al iniciar el servidor.
- Usa el archivo de configuración:  
  `/home/ec2-user/.config/ngrok/ngrok.yml`
- Apunta al puerto interno `8191` donde corre Streamlit.
- Mantiene un dominio fijo asignado por Ngrok.

Comandos útiles:

| Acción | Comando |
|--------|---------|
| Ver estado | `sudo systemctl status ngrok` |
| Reiniciar ngrok | `sudo systemctl restart ngrok` |
| Detener | `sudo systemctl stop ngrok` |
| Ver logs en tiempo real | `sudo journalctl -u ngrok -f` |

> ✅ Con esta configuración, no es necesario ejecutar ngrok manualmente — siempre arrancará junto con el servidor.



👨‍💻 Autor: Jorge Pérez
"""
