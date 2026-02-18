import boto3

# cliente Bedrock
client = boto3.client("bedrock", region_name="us-east-1")

# Parámetros del nuevo perfil
inference_profile_name = "MIU-Global-crossregion-claudesonnet46"
description = "Asistente MiU usando Claude Sonnet 4.6 "
model_source = {
    "copyFrom": "arn:aws:bedrock:us-east-1:552102268375:inference-profile/global.anthropic.claude-sonnet-4-6"
}
tags = [
        {"key": "chatbot", "value": "MIU"},
        {"key": "componente_chatbot", "value": "modelo_lenguaje_claude46sonnet"}
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


# ARN: arn:aws:bedrock:us-east-1:552102268375:application-inference-profile/ms770l3o5ywq //18_02_2026