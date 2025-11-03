# ⚙️ Servicio systemd para API Flask de conversión con LibreOffice

Este documento describe la creación y activación del servicio `flaskconvert.service`, encargado de ejecutar de forma automática y persistente la API Flask que realiza conversiones de archivos utilizando LibreOffice en el servidor ARM (t4g.medium).

---

## 📁 1. Ubicación del script Flask

Ruta del archivo ejecutado por el servicio:

```
/root/libreoffice_converter_api.py
```

Permisos recomendados:

```
sudo chown root:root /root/libreoffice_converter_api.py
sudo chmod 644 /root/libreoffice_converter_api.py
```

---

## 📝 2. Crear el archivo de servicio systemd

```
sudo nano /etc/systemd/system/flaskconvert.service
```

Contenido literal del servicio:

```
[Unit]
Description=Servidor Flask para conversión con LibreOffice
After=network.target

[Service]
User=root
WorkingDirectory=/root
ExecStart=/usr/local/bin/python3.11 /root/libreoffice_converter_api.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Guardar con: `CTRL+O`, `ENTER`, `CTRL+X`

---

## 🔄 3. Recargar systemd y habilitar servicio

```
sudo systemctl daemon-reload
sudo systemctl enable flaskconvert.service
sudo systemctl start flaskconvert.service
```

---

## ✅ 4. Comprobar estado del servicio

```
sudo systemctl status flaskconvert.service
```

Salida esperada:

```
● flaskconvert.service - Servidor Flask para conversión con LibreOffice
   Loaded: loaded (/etc/systemd/system/flaskconvert.service; enabled)
   Active: active (running)
```

---

## 🛰️ 5. Ver logs en tiempo real (opcional)

```
sudo journalctl -u flaskconvert.service -f
```

---

## 🧪 6. Probar la API con `curl`

```
curl -X POST http://localhost:5001/convert \
  -H "Content-Type: application/json" \
  -d '{"input_path": "/home/ec2-user/n8n_files/test.txt", "output_format": "pdf"}'
```

Salida esperada:

```
{
  "message": "Conversión a pdf exitosa",
  "output_path": "/home/ec2-user/n8n_files/conversions/test.pdf"
}
```

---

## 🏁 Estado final

| Elemento | Estado |
|----------|--------|
| Script Flask en `/root/` | ✅ |
| Servicio systemd creado | ✅ |
| Servicio activo y persistente | ✅ |
| Conversión accesible vía API HTTP | ✅ |

---
