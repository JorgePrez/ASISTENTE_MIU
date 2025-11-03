# 🧹 Limpieza automática de archivos temporales de conversión (LibreOffice + n8n)

Este proceso elimina **todos los archivos generados temporalmente** en:

- `/home/ec2-user/n8n_files/uploads`
- `/home/ec2-user/n8n_files/conversions`

La limpieza se ejecuta **todos los días a medianoche (00:00)** mediante `cron`, evitando que el servidor acumule archivos innecesarios.

---

## 📂 1. Estructura de carpetas

```bash
sudo mkdir -p /home/ec2-user/n8n_files/uploads
sudo mkdir -p /home/ec2-user/n8n_files/conversions
sudo chmod -R 755 /home/ec2-user/n8n_files
```

Opcional: crear un `.gitkeep` para evitar que la carpeta quede vacía en Git.

---

## 📝 2. Crear el script de limpieza

```bash
sudo tee /usr/local/bin/cleanup_n8n_files.sh >/dev/null <<'SH'
#!/usr/bin/env bash
set -euo pipefail

# Carpetas a limpiar
DIRS=(
"/home/ec2-user/n8n_files/uploads"
"/home/ec2-user/n8n_files/conversions"
)

# Permite prueba en seco si ejecutas: DRY_RUN=1 /usr/local/bin/cleanup_n8n_files.sh
DRY="${DRY_RUN:-0}"

for D in "${DIRS[@]}"; do
  # Borra solo archivos (evita .gitkeep si lo usas)
  if [[ "$DRY" == "1" ]]; then
    find "$D" -type f ! -name '.gitkeep' -print
  else
    find "$D" -type f ! -name '.gitkeep' -print -delete
  fi

  # Limpia subcarpetas vacías
  if [[ "$DRY" == "1" ]]; then
    find "$D" -type d -empty -mindepth 1 -print
  else
    find "$D" -type d -empty -mindepth 1 -print -delete
  fi
done
SH
```

Dar permisos de ejecución:

```bash
sudo chmod +x /usr/local/bin/cleanup_n8n_files.sh
```

---

## 🧪 3. Probar manualmente

```bash
sudo /usr/local/bin/cleanup_n8n_files.sh
```

O bien ejecutar en modo simulación (no borra nada):

```bash
DRY_RUN=1 sudo /usr/local/bin/cleanup_n8n_files.sh
```

---

## ⏰ 4. Instalar `cron` y habilitar tarea diaria

```bash
sudo dnf install -y cronie
sudo systemctl enable crond
sudo systemctl start crond
sudo systemctl status crond
```

Agregar tarea que corre cada medianoche:

```bash
sudo bash -c '(crontab -l 2>/dev/null; \
echo "CRON_TZ=America/Guatemala"; \
echo "0 0 * * * /usr/local/bin/cleanup_n8n_files.sh >> /var/log/cleanup_n8n.log 2>&1") | crontab -'
```

Verificar que el cron quedó instalado:

```bash
sudo crontab -l
```

Salida esperada:

```
CRON_TZ=America/Guatemala
0 0 * * * /usr/local/bin/cleanup_n8n_files.sh >> /var/log/cleanup_n8n.log 2>&1
```

---

## 📜 5. Logs de ejecución

El script genera un log en:

```
/var/log/cleanup_n8n.log
```

Ver log:

```bash
sudo tail -f /var/log/cleanup_n8n.log
```

---

## ✅ Resultado

✔ Evita acumulación de archivos temporales  
✔ Mantiene limpio el disco sin intervención manual  
✔ Integrado con LibreOffice + Flask + n8n  
✔ Corre automáticamente todos los días

---

## 🔄 Reinstalar / eliminar cron (si fuera necesario)

Eliminar la regla programada:

```bash
sudo crontab -r
```

---

## 📌 Notas

- Si se agregan nuevas carpetas temporales pueden añadirse al array `DIRS=()`
- `DRY_RUN=1` es útil antes de producción
- Asegura que `crond` está siempre activo: `systemctl status crond`

---
