import re
from decimal import Decimal
import boto3
import pandas as pd

REGION = "us-east-1"
TABLE  = "CHHSessionTablePruebas"

# --- Helpers ---
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
    if not isinstance(chat, list):
        return 0
    c = 0
    for msg in chat:
        if isinstance(msg, dict) and "role" in msg:
            role = msg["role"]
            if isinstance(role, dict) and "S" in role:
                role = role["S"]
            if isinstance(role, str) and role.lower() == "user":
                c += 1
            continue
        if isinstance(msg, dict) and "M" in msg and isinstance(msg["M"], dict):
            m = msg["M"]
            role = m.get("role")
            if isinstance(role, dict) and "S" in role:
                role = role["S"]
            if isinstance(role, str) and role.lower() == "user":
                c += 1
    return c

# --- Dynamo ---
dynamodb = boto3.resource("dynamodb", region_name=REGION)
table = dynamodb.Table(TABLE)

items = scan_all(
    table,
    projection_expression="#pk, #sk, #created, #chat",
    ean={"#pk": "PK", "#sk": "SK", "#created": "CreatedAt", "#chat": "Chat"},
)

# --- DataFrame ---
df = pd.DataFrame(items)
df["CreatedAt"] = pd.to_datetime(df["CreatedAt"], utc=True, errors="coerce")
df["UserEmail"] = df["PK"].map(extract_email)
df["UserQuestions"] = df["Chat"].map(count_user_msgs)

# --- Solo agosto 2025 ---
start = pd.Timestamp("2025-08-01", tz="UTC")
end   = pd.Timestamp("2025-09-01", tz="UTC")
dfa = df[(df["CreatedAt"] >= start) & (df["CreatedAt"] < end)].copy()
dfa["Month"] = dfa["CreatedAt"].dt.to_period("M").astype(str)

# --- Métricas ---
total_conversaciones = len(dfa)
usuarios_unicos = dfa["UserEmail"].nunique()
total_preguntas_usuario = int(dfa["UserQuestions"].sum())

print("=== AGOSTO 2025 ===")
print(f"Conversaciones totales: {total_conversaciones}")
print(f"Usuarios únicos: {usuarios_unicos}")
print(f"Preguntas de usuario totales: {total_preguntas_usuario}")

# Listado detalle
conversaciones = dfa[["CreatedAt", "UserEmail", "SK", "UserQuestions"]].sort_values(
    ["CreatedAt","UserEmail"]
).reset_index(drop=True)

print("\nPrimeras filas de agosto:")
print(conversaciones.head(20).to_string(index=False))

# Opcional: exportar
# conversaciones.to_csv("agosto_conversaciones.csv", index=False)
