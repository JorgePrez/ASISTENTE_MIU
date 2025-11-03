# 🚀 Guía de Instalación de n8n con Docker + Nginx + HTTPS (Let's Encrypt)

Esta guía documenta cómo desplegar n8n en **Amazon Linux 2023 (EC2)** usando:
- Docker
- Nginx como reverse proxy
- Certbot para HTTPS automático
- LibreOffice opcional para conversiones de documentos

---

## ✅ 1. Requisitos

| Componente | Versión / Nota |
|------------|----------------|
| Sistema    | Amazon Linux 2023 (ARM o x86) |
| Dominio    | Apuntado a la IP pública del servidor |
| Docker     | Instalado y funcionando |
| Puerto     | 80 y 443 abiertos en el Security Group |

---

## 🐳 2. Instalar Docker (si aún no está instalado)

```bash
sudo dnf install -y docker
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user
```

*Cerrar y abrir sesión para aplicar permisos del grupo docker.*

---

## 📁 3. Crear carpetas de n8n

```bash
mkdir -p /home/ec2-user/n8n_files
mkdir -p /opt/libreoffice25.8   # Opcional si usará LibreOffice
```

---

## 🧱 4. Ejecutar contenedor de n8n

```bash
docker run -d \
  --name n8n \
  -p 5678:5678 \
  -v /home/ec2-user/n8n_files:/home/ec2-user/n8n_files \
  -v /root/.n8n:/root/.n8n \
  -v /opt/libreoffice25.8:/opt/libreoffice25.8 \
  -e N8N_HOST=awsn8nflujos.zapto.org \
  -e WEBHOOK_TUNNEL_URL=https://awsn8nflujos.zapto.org/ \
  -e WEBHOOK_URL=https://awsn8nflujos.zapto.org/ \
  -e NODE_ENV=production \
  -e GENERIC_TIMEZONE=America/Guatemala \
  -e N8N_CONCURRENCY_PRODUCTION_LIMIT=1 \
  --restart unless-stopped \
  n8nio/n8n:latest
```

Verificar que está corriendo:

```bash
docker ps
```

Probar acceso interno:

```bash
curl -I http://localhost:5678
```

---

## 🌐 5. Instalar y configurar Nginx como reverse proxy

```bash
sudo dnf install -y nginx
sudo systemctl enable --now nginx
```

Crear archivo de configuración:

```bash
sudo nano /etc/nginx/conf.d/n8n.conf
```

Contenido:

```nginx
server {
    listen 80;
    server_name awsn8nflujos.zapto.org;

    location / {
        proxy_pass http://localhost:5678;
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
        proxy_buffering off;
        proxy_cache off;

        proxy_set_header Connection 'Upgrade';
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Probar configuración:

```bash
sudo nginx -t
sudo systemctl restart nginx
```

---

## 🔐 6. Activar HTTPS con Certbot

```bash
sudo dnf install -y certbot python3-certbot-nginx
sudo certbot --nginx -d awsn8nflujos.zapto.org
```

Certbot modificará el archivo automáticamente para agregar SSL.

Reiniciar Nginx:

```bash
sudo systemctl restart nginx
```

---

## ✅ 7. Prueba final

Abrir en navegador:

```
https://awsn8nflujos.zapto.org
```

Si ves la pantalla de login inicial de n8n → ¡funciona! 🎉

---

## 🧯 8. Comandos útiles

| Acción | Comando |
|--------|---------|
| Ver logs | `docker logs -f n8n` |
| Reiniciar contenedor | `docker restart n8n` |
| Actualizar n8n | `docker pull n8nio/n8n:latest && docker stop n8n && docker rm n8n && <docker run de nuevo>` |
| Ver Nginx estado | `sudo systemctl status nginx` |
| Renovar SSL manualmente | `sudo certbot renew --dry-run` |

---

## 📌 Nota opcional: uso de LibreOffice en n8n

Solo aplica si usas workflows que convierten DOCX→PDF, PPTX→PDF, etc.

Montaste LibreOffice en:

```
/opt/libreoffice25.8
```

En n8n usa la ruta:

```
/opt/libreoffice25.8/program/soffice
```

---

## 🎯 Fin

Sistema productivo funcionando con:

✅ n8n en Docker  
✅ Reverse proxy con Nginx  
✅ HTTPS automático con Certbot  
✅ Carpetas persistentes  
✅ Ready para producción  
