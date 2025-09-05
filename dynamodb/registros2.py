import re
from decimal import Decimal
import boto3
import pandas as pd

REGION = "us-east-1"
TABLE  = "CHHSessionTablePruebas"

# ---------- Helpers ----------
def to_builtin(o):
    if isinstance(o, Decimal):
        return int(o) if o % 1 == 0 else float(o)
    if isinstance(o, list):
        return [to_builtin(x) for x in o]
    if isinstance(o, dict):
        return {k: to_builtin(v) for k, v in o.items()}
    return o

def scan_all(table, projection_expression=None, ean=None):
    kwargs = {}
    if projection_expression:
        kwargs["ProjectionExpression"] = projection_expression
    if ean:
        kwargs["ExpressionAttributeNames"] = ean

    items, lek = [], None
    while True:
        if lek:
            kwargs["ExclusiveStartKey"] = lek
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        lek = resp.get("LastEvaluatedKey")
        if not lek:
            break
    return [to_builtin(x) for x in items]

def extract_email(pk):
    m = re.search(r"USER#(.+?)#AUTHOR#", pk or "")
    return m.group(1).lower() if m else None

def count_user_msgs(chat):
    """
    Cuenta mensajes con role=='user' en diferentes representaciones:
    - [{'role': 'user', 'content': '...'}, ...]
    - [{'M': {'role': {'S':'user'}, 'content': {'S':'...'}}}, ...]  (vista cruda tipo consola)
    - role puede venir en minúsculas o mayúsculas
    """
    if not isinstance(chat, list):
        return 0
    c = 0
    for msg in chat:
        # Caso normal (ya deserializado)
        if isinstance(msg, dict) and "role" in msg:
            role = msg["role"]
            if isinstance(role, dict) and "S" in role:
                role = role["S"]
            if isinstance(role, str) and role.lower() == "user":
                c += 1
            continue
        # Caso con 'M'
        if isinstance(msg, dict) and "M" in msg and isinstance(msg["M"], dict):
            m = msg["M"]
            role = m.get("role")
            if isinstance(role, dict) and "S" in role:
                role = role["S"]
            if isinstance(role, str) and role.lower() == "user":
                c += 1
    return c

# ---------- Dynamo ----------
dynamodb = boto3.resource("dynamodb", region_name=REGION)
table = dynamodb.Table(TABLE)

# Traemos solo lo necesario: PK, SK, CreatedAt, Chat
items = scan_all(
    table,
    projection_expression="#pk, #sk, #created, #chat",
    ean={"#pk": "PK", "#sk": "SK", "#created": "CreatedAt", "#chat": "Chat"},
)

# ---------- DataFrame ----------
df = pd.DataFrame(items)
df["CreatedAt"] = pd.to_datetime(df["CreatedAt"], utc=True, errors="coerce")
df["UserEmail"] = df["PK"].map(extract_email)
df["UserQuestions"] = df["Chat"].map(count_user_msgs)

# Filtro JULIO y AGOSTO 2025 (ajusta año si hace falta)
start = pd.Timestamp("2025-07-01", tz="UTC")
end   = pd.Timestamp("2025-09-01", tz="UTC")  # exclusivo
dfa = df[(df["CreatedAt"] >= start) & (df["CreatedAt"] < end)].copy()

# Mes (YYYY-MM)
dfa["Month"] = dfa["CreatedAt"].dt.to_period("M").astype(str)

# --------- Métricas pedidas ---------
# Conversaciones (filas) y usuarios únicos ya los tenías; aquí añadimos preguntas de usuario
total_preguntas_usuario = int(dfa["UserQuestions"].sum())
preguntas_usuario_por_mes = dfa.groupby("Month")["UserQuestions"].sum().astype(int).sort_index()

# (por si también quieres conservar las agregaciones previas)
conversaciones_por_mes = dfa["Month"].value_counts().sort_index()
usuarios_unicos_por_mes = dfa.groupby("Month")["UserEmail"].nunique().sort_index()

print("=== JULIO + AGOSTO ===")
print(f"Total de preguntas de usuario: {total_preguntas_usuario}\n")

print("Preguntas de usuario por mes:")
print(preguntas_usuario_por_mes.to_string(), "\n")

print("Conversaciones por mes:")
print(conversaciones_por_mes.to_string(), "\n")

print("Usuarios únicos por mes:")
print(usuarios_unicos_por_mes.to_string(), "\n")

# Listado “conversaciones” sin Name/autor, con conteo de preguntas por conversación
conversaciones = dfa[["CreatedAt","Month","UserEmail","SK","UserQuestions"]].sort_values(
    ["CreatedAt","UserEmail"]
).reset_index(drop=True)

# Opcional: exportar a Excel
# with pd.ExcelWriter("julio_agosto_conversaciones.xlsx") as w:
#     conversaciones.to_excel(w, sheet_name="Conversaciones", index=False)
#     (pd.DataFrame({
#         "Conversaciones por mes": conversaciones_por_mes,
#         "Usuarios únicos por mes": usuarios_unicos_por_mes,
#         "Preguntas usuario por mes": preguntas_usuario_por_mes
#      })).to_excel(w, sheet_name="Resumen")
