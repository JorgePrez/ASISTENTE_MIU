import boto3

# Configura tu cliente Bedrock
client = boto3.client("bedrock", region_name="us-east-1")

# Parámetros del nuevo perfil
inference_profile_name = "MIU-claude35"
description = "MIU usando Claude 3.5 para nombrar conversaciones"
model_source = {
    "copyFrom": "arn:aws:bedrock:us-east-1:552102268375:inference-profile/us.anthropic.claude-3-5-sonnet-20240620-v1:0"
}
tags = [
        {"key": "chatbot", "value": "MIU"},
        {"key": "componente_chatbot", "value": "modelo_lenguaje_claude3_5"}
]

# Crear el perfil
response = client.create_inference_profile(
    inferenceProfileName=inference_profile_name,
    description=description,
    modelSource=model_source,
    tags=tags
)

# Mostrar el ARN del nuevo perfil
print("Inference profile creado exitosamente:")
print("ARN:", response["inferenceProfileArn"])
