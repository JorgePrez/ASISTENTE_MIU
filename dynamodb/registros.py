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

def scan_all(table, projection_expression=None):
    kwargs = {}
    if projection_expression:
        kwargs["ProjectionExpression"] = projection_expression
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

# --- Dynamo ---
dynamodb = boto3.resource("dynamodb", region_name=REGION)
table = dynamodb.Table(TABLE)

# Solo traemos columnas necesarias
items = scan_all(table, projection_expression="PK, SK, CreatedAt")

# --- DataFrame base ---
df = pd.DataFrame(items)
df["CreatedAt"] = pd.to_datetime(df["CreatedAt"], utc=True, errors="coerce")

# Extraer email de PK
def extract_email(pk):
    m = re.search(r"USER#(.+?)#AUTHOR#", pk or "")
    return m.group(1).lower() if m else None

df["UserEmail"] = df["PK"].map(extract_email)

# Filtrar JULIO y AGOSTO
start = pd.Timestamp("2025-07-01", tz="UTC")
end   = pd.Timestamp("2025-09-01", tz="UTC")  # exclusivo
dfa = df[(df["CreatedAt"] >= start) & (df["CreatedAt"] < end)].copy()

# Columna mes
dfa["Month"] = dfa["CreatedAt"].dt.to_period("M").astype(str)

# --- Resúmenes ---
total_conversaciones = len(dfa)
usuarios_unicos_total = dfa["UserEmail"].nunique()
conversaciones_por_mes = dfa["Month"].value_counts().sort_index()
usuarios_por_mes = dfa.groupby("Month")["UserEmail"].nunique().sort_index()

print("=== RESUMEN JULIO+AGOSTO ===")
print(f"Conversaciones totales: {total_conversaciones}")
print(f"Usuarios únicos totales: {usuarios_unicos_total}\n")

print("Conversaciones por mes:")
print(conversaciones_por_mes.to_string(), "\n")

print("Usuarios únicos por mes:")
print(usuarios_por_mes.to_string(), "\n")

# --- Conversaciones (listado final) ---
conversaciones_cols = ["CreatedAt", "Month", "UserEmail", "SK"]
conversaciones = dfa[conversaciones_cols].sort_values(
    ["CreatedAt", "UserEmail"]
).reset_index(drop=True)

# Opcional: exportar a Excel
# with pd.ExcelWriter("conversaciones_julio_agosto.xlsx") as writer:
#     conversaciones.to_excel(writer, sheet_name="Conversaciones", index=False)
#     pd.DataFrame({
#         "Conversaciones por mes": conversaciones_por_mes,
#         "Usuarios únicos por mes": usuarios_por_mes
#     }).to_excel(writer, sheet_name="Resumen")


