import boto3
import csv
from datetime import datetime
from collections import defaultdict

TABLE_NAME = "CHHSessionTablePruebas"
FECHA_INICIO = datetime(2025, 8, 1)
NOMBRE_CSV = "metricas_chatbot_desde_agosto.csv"

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

total_conversaciones = 0
usuarios_unicos = set()
fecha_min = None
fecha_max = None
total_preguntas = 0  # ✅ Renombrado

# Métricas mensuales
metricas_por_mes = defaultdict(lambda: {
    "conversaciones": 0,
    "usuarios": set(),
    "preguntas": 0
})

# Escanear tabla
response = table.scan()
items = response.get("Items", [])

while True:
    for item in items:
        # === Fecha ===
        created_at_str = item.get("CreatedAt")
        if not created_at_str:
            continue

        try:
            fecha = datetime.fromisoformat(created_at_str)
        except Exception:
            continue

        # Filtrar fechas anteriores a la puesta en producción
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

        # === Contar preguntas (role = user) ===
        preguntas = 0
        chat = item.get("Chat", [])
        if isinstance(chat, list):
            for mensaje in chat:
                if isinstance(mensaje, dict):
                    if mensaje.get("role") == "user":
                        preguntas += 1

        total_preguntas += preguntas
        metricas_por_mes[clave_mes]["conversaciones"] += 1
        metricas_por_mes[clave_mes]["usuarios"].add(usuario)
        metricas_por_mes[clave_mes]["preguntas"] += preguntas

    # Paginación
    if 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        items = response.get("Items", [])
    else:
        break

# === 📊 Totales globales ===
print("\n📊 RESUMEN GLOBAL (desde 2025-08-01)")
print(f"Cantidad total de preguntas realizadas: {total_preguntas}")
print(f"Conversaciones: {total_conversaciones}")
print(f"Usuarios únicos: {len(usuarios_unicos)}")
print(f"Rango de fechas: {fecha_min} → {fecha_max}")

# === 📅 Métricas por mes ===
print("\n📆 MÉTRICAS POR MES")
for mes in sorted(metricas_por_mes.keys()):
    datos = metricas_por_mes[mes]
    print(f"{mes}: {datos['preguntas']} preguntas, "
          f"{datos['conversaciones']} conversaciones, "
          f"{len(datos['usuarios'])} usuarios")

# === 🧾 Exportar a CSV ===
with open(NOMBRE_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "Cantidad total de preguntas realizadas",
        "Conversaciones",
        "Usuarios"
    ])

    # Datos por mes
    for mes in sorted(metricas_por_mes.keys()):
        datos = metricas_por_mes[mes]
        writer.writerow([
            datos["preguntas"],
            datos["conversaciones"],
            len(datos["usuarios"])
        ])

    # Fila de totales
    writer.writerow([
        total_preguntas,
        total_conversaciones,
        len(usuarios_unicos)
    ])

print(f"\n✅ Archivo CSV generado: {NOMBRE_CSV}")
