import boto3
import json
from botocore.exceptions import ClientError
from datetime import datetime
from boto3.dynamodb.conditions import Attr  
import config.model_ia_cimps_streaming as model  # para usar model.generate_name

# Inicializar recurso de DynamoDB
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
table = dynamodb.Table("AsistenteMiuCursosImpartidos")

# Simulación simple (puedes reemplazar con acceso a tabla "users" si la usas)
def getUser(user_id):
    return user_id

def save(chat_id, user_id, curso_impartido_id, name, chat):
    item = {
        "PK": f"USER#{user_id}#CIMP#{curso_impartido_id}",
        "SK": f"CHAT#{chat_id}",
        "Name": name,
        "Chat": chat,
        "CreatedAt": datetime.utcnow().isoformat()
    }
    table.put_item(Item=item)

def edit(chat_id, chat, user_id, curso_impartido_id):
    table.update_item(
        Key={"PK": f"USER#{user_id}#CIMP#{curso_impartido_id}", "SK": f"CHAT#{chat_id}"},
        UpdateExpression="SET Chat = :chat",
        ExpressionAttributeValues={":chat": chat}
    )

def getChats(user_id, curso_impartido_id):
    try:
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("PK").eq(f"USER#{user_id}#CIMP#{curso_impartido_id}"),
            FilterExpression=Attr("IsDeleted").not_exists() | Attr("IsDeleted").eq(False),  # ✅ (2) agregar
            ScanIndexForward=False  # Orden descendente
        )
        data = response.get("Items", [])
        for item in data:
            chat = item.get("Chat")
            if isinstance(chat, str):
                try:
                    item["Chat"] = json.loads(chat)
                except json.JSONDecodeError:
                    item["Chat"] = []
            elif not chat:
                item["Chat"] = []

        data.sort(key=lambda x: x.get("CreatedAt", ""), reverse=True)
        return data
    except ClientError as e:
        print("Error en getChats:", e)
        return []

def delete(chat_id, user_id, curso_impartido_id):
    table.update_item(  # ✅ (3) reemplazar delete_item por update_item
        Key={"PK": f"USER#{user_id}#CIMP#{curso_impartido_id}", "SK": f"CHAT#{chat_id}"},
        UpdateExpression="SET IsDeleted = :d, DeletedAt = :ts",
        ExpressionAttributeValues={
            ":d": True,
            ":ts": datetime.utcnow().isoformat()
        }
    )

def editName(chat_id, prompt, user_id, curso_impartido_id):
    name = model.generate_name(prompt)
    table.update_item(
        Key={"PK": f"USER#{user_id}#CIMP#{curso_impartido_id}", "SK": f"CHAT#{chat_id}"},
        UpdateExpression="SET #n = :name",
        ExpressionAttributeNames={"#n": "Name"},
        ExpressionAttributeValues={":name": name}
    )

def editNameManual(chat_id, new_name, user_id, curso_impartido_id):
    table.update_item(
        Key={"PK": f"USER#{user_id}#CIMP#{curso_impartido_id}", "SK": f"CHAT#{chat_id}"},
        UpdateExpression="SET #n = :name",
        ExpressionAttributeNames={"#n": "Name"},
        ExpressionAttributeValues={":name": new_name}
    )

def getNameChat(chat_id, user_id, curso_impartido_id):
    try:
        response = table.get_item(
            Key={"PK": f"USER#{user_id}#CIMP#{curso_impartido_id}", "SK": f"CHAT#{chat_id}"}
        )
        return response["Item"]["Name"]
    except KeyError:
        return None
