import boto3

# =============================
# CONFIGURACIÓN
# =============================
#TABLE_NAME = "CHHSessionTablePruebas"   #  ÚNICA VARIABLE

TABLE_NAME = "AsistenteMiuCursosImpartidos"   #  ÚNICA VARIABLE


#TABLE_NAME= "ProcesosSessionTable"


REGION = "us-east-1"                    # ajusta si usas otra

# =============================
# DYNAMODB
# =============================
dynamodb = boto3.resource("dynamodb", region_name=REGION)
table = dynamodb.Table(TABLE_NAME)

usuarios_unicos = set()
total_items = 0

# =============================
# SCAN COMPLETO
# =============================
response = table.scan()
items = response.get("Items", [])

while True:
    for item in items:
        total_items += 1

        pk = item.get("PK", "")
        if not pk:
            continue

        # PK esperadas:
        # USER#20230676#CIMP#144827
        # USER#gabriel.sican@ufm.edu#AUTHOR#general
        # USER#diegovillela@ufm.edu
        parts = pk.split("#")

        if len(parts) >= 2 and parts[0] == "USER":
            usuario = parts[1].strip()
            if usuario:
                usuarios_unicos.add(usuario)

    if "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        items = response.get("Items", [])
    else:
        break

# =============================
# RESULTADO
# =============================
print("\n📊 USUARIOS ÚNICOS GLOBALES")
print(f"Tabla: {TABLE_NAME}")
print(f"Usuarios únicos reales: {len(usuarios_unicos)}")

