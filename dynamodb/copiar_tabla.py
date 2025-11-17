import boto3
from boto3.dynamodb.conditions import Key, Attr

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

TABLE_ORIGEN = "AsistenteMiuCursosImpartidos"
TABLE_DESTINO = "AsistenteMiuCursosImpartidosCompras"

table_origen = dynamodb.Table(TABLE_ORIGEN)
table_destino = dynamodb.Table(TABLE_DESTINO)

def copiar_items():
    response = table_origen.scan()
    items = response["Items"]

    # paginación
    while "LastEvaluatedKey" in response:
        response = table_origen.scan(
            ExclusiveStartKey=response["LastEvaluatedKey"]
        )
        items.extend(response["Items"])

    print(f"Total items a copiar: {len(items)}")

    for item in items:
        table_destino.put_item(Item=item)

    print("Copia completada.")

copiar_items()
