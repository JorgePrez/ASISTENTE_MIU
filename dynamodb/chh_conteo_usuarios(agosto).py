import boto3
from datetime import datetime
from collections import defaultdict

TABLE_NAME = "CHHSessionTablePruebas"
FECHA_INICIO = datetime(2025, 8, 1)  # 📅 Fecha de inicio en producción

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

total_conversaciones = 0
usuarios_unicos = set()
fecha_min = None
fecha_max = None
total_interacciones_user = 0

# Métricas mensuales
metricas_por_mes = defaultdict(lambda: {
    "conversaciones": 0,
    "usuarios": set(),
    "total_interacciones_user": 0
})

# Escanear tabla
response = table.scan()
items = response.get("Items", [])

while True:
    for item in items:
        # === Fecha ===
        created_at_str = item.get("CreatedAt")
        if not created_at_str:
            continue  # ignorar sin fecha

        try:
            fecha = datetime.fromisoformat(created_at_str)
        except Exception:
            continue  # ignorar fechas inválidas

        # ❌ Saltar si la fecha es anterior a la puesta en producción
        if fecha < FECHA_INICIO:
            continue

        total_conversaciones += 1

        # === Usuario ===
        pk = item.get("PK", "")
        usuario = pk.split("#")[1] if "#" in pk else pk
        usuarios_unicos.add(usuario)

        # Rango de fechas real
        if not fecha_min or fecha < fecha_min:
            fecha_min = fecha
        if not fecha_max or fecha > fecha_max:
            fecha_max = fecha

        clave_mes = fecha.strftime("%Y-%m")

        # === Interacciones user ===
        interacciones_user = 0
        chat = item.get("Chat", [])
        if isinstance(chat, list):
            for mensaje in chat:
                if isinstance(mensaje, dict):
                    if mensaje.get("role") == "user":
                        interacciones_user += 1

        total_interacciones_user += interacciones_user
        metricas_por_mes[clave_mes]["conversaciones"] += 1
        metricas_por_mes[clave_mes]["usuarios"].add(usuario)
        metricas_por_mes[clave_mes]["total_interacciones_user"] += interacciones_user

    # Paginación
    if 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        items = response.get("Items", [])
    else:
        break

# === 📊 Totales globales ===
print("\n📊 RESUMEN GLOBAL (desde 2025-08-01)")
print(f"Total de conversaciones: {total_conversaciones}")
print(f"Usuarios únicos: {len(usuarios_unicos)}")
print(f"Rango de fechas: {fecha_min} → {fecha_max}")
print(f"Total interacciones 'user': {total_interacciones_user}")

# === 📅 Métricas por mes ===
print("\n📆 MÉTRICAS POR MES")
for mes in sorted(metricas_por_mes.keys()):
    datos = metricas_por_mes[mes]
    print(f"{mes}: {datos['conversaciones']} conversaciones, "
          f"{len(datos['usuarios'])} usuarios únicos, "
          f"{datos['total_interacciones_user']} interacciones user")
