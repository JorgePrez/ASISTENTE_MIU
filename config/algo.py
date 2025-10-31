

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableParallel
from langchain_core.output_parsers import StrOutputParser
from langchain_aws import AmazonKnowledgeBasesRetriever, ChatBedrock
from operator import itemgetter
import boto3
from langchain_aws import ChatBedrock
from typing import List, Dict
from pydantic import BaseModel
import boto3
from botocore.exceptions import NoCredentialsError

import botocore
#from langchain.callbacks.tracers.run_collector import collect_runs



IS_TESTING = False  # Cambiar a False para producción


# ✅ Importar solo en producción
if not IS_TESTING:
    from langchain.callbacks import collect_runs

session = boto3.Session(profile_name="testing" if IS_TESTING else None)


sts = session.client("sts")

identity = sts.get_caller_identity()
print(f"🔍 Ejecutando como: {identity['Arn']}")
print(f"🧾 Cuenta AWS: {identity['Account']}")


bedrock_runtime = session.client(
        service_name="bedrock-runtime",
        region_name="us-east-1"
    )

model_kwargs = {
    "max_tokens": 4096,
    "temperature": 0.0,
    "top_k": 250,
    "top_p": 1,
    "stop_sequences": ["\n\nHuman"],
}

# ✅ IDs de modelos según entorno
if IS_TESTING:
    model_id_3_7 = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
    model_id_3_5 = "us.anthropic.claude-3-5-sonnet-20240620-v1:0"
else:
    model_id_3_7 = "arn:aws:bedrock:us-east-1:552102268375:application-inference-profile/ssbzqg79e5dm"
    model_id_3_5 = "arn:aws:bedrock:us-east-1:552102268375:application-inference-profile/3zu0zc2t66sj"



# ✅ Modelo Claude 3.7 Sonnet (para la chain principal)
model = ChatBedrock(
    client=bedrock_runtime,
    model_id=model_id_3_7,
    model_kwargs=model_kwargs,
    provider="anthropic"
)

# ✅ Modelo Claude 3.5 Sonnet (para renombrar)
modelNames = ChatBedrock(
    client=bedrock_runtime,
    model_id=model_id_3_5,
    model_kwargs=model_kwargs,
    provider="anthropic"
)


#inference_profile3_5claudehaiku="us.anthropic.claude-3-5-haiku-20241022-v1:0"
#inference_profile3claudehaiku="us.anthropic.claude-3-haiku-20240307-v1:0"
#inference_profile3_5Sonnet="us.anthropic.claude-3-5-sonnet-20240620-v1:0"
#inference_profile3_7Sonnet="us.anthropic.claude-3-7-sonnet-20250219-v1:0"


#inference_profile3_7Sonnet="arn:aws:bedrock:us-east-1:552102268375:application-inference-profile/tcsgx7nj4mf1"

import re

from urllib.parse import urlparse


def _extraer_nombre_archivo(uri: str) -> str:
    if not uri:
        return ""
    p = urlparse(uri)
    path = p.path if p.scheme else uri
    path = path.rstrip("/")
    filename = path.split("/")[-1] if path else ""

    # 🔹 Quitar el prefijo tipo "miuDocumento_972528_"
    filename = re.sub(r"^miuDocumento_\d+_", "", filename)

    return filename

###########################################
SYSTEM_PROMPT_ASISTENTE_CIMPS = (f"""
## Base de conocimientos (solo puedes responder con esta información):

{{context}}
                          
---
....
    """
    )


def create_prompt_template_procesos():
    return ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT_ASISTENTE_CIMPS),
            MessagesPlaceholder(variable_name="historial"),
            ("human", "{question}")
        ]
    )


def limpiar_metadata_retrieved(docs):
    for doc in docs:
        # 1. Limpiar metadata directa
        #,"score"
        for clave in ["x-amz-bedrock-kb-data-source-id", "x-amz-bedrock-kb-source-uri","x-amz-bedrock-kb-document-page-number" ,"location" , "type", "score"]:
            doc.metadata.pop(clave, None)


        # 2. Limpiar metadata anidada dentro de source_metadata
        sm = doc.metadata.get("source_metadata")
        if isinstance(sm, dict):
            # Verificar si existe nombre_archivo_original y no está vacío
            nombre_original = sm.get("nombre_archivo_original")
            if nombre_original:
                sm["nombre_archivo"] = nombre_original
            else:
                sm["nombre_archivo"] = _extraer_nombre_archivo(
                    sm.get("x-amz-bedrock-kb-source-uri", "")
                )

            # Limpiar claves innecesarias
            for clave in [
                "nombre_archivo_original",
                "x-amz-bedrock-kb-data-source-id",
                "miu_documentos",
                "x-amz-bedrock-kb-document-page-number",
                "curso_impartido",
                "x-amz-bedrock-kb-source-uri",
            ]:
                sm.pop(clave, None)


    return docs

# Base de conocimiento en Bedrock
BASE_CONOCIMIENTOS_CIMPS = "ZLSIIBQ6B3" 



def generar_configuracion_retriever(curso_impartido: str) -> dict:
    config = {
        "vectorSearchConfiguration": {
            "numberOfResults": 100,
            "rerankingConfiguration": {
                "bedrockRerankingConfiguration": {
                    "modelConfiguration": {
                        "modelArn": "arn:aws:bedrock:us-west-2::foundation-model/cohere.rerank-v3-5:0",
                    },
                    "numberOfRerankedResults": 20,
                    "metadataConfiguration": {
                        "selectionMode": "SELECTIVE",
                        "selectiveModeConfiguration": {
                            "fieldsToInclude": [
                                    {"fieldName": "titulo"},
                                    {"fieldName": "descripcion"},
                                    {"fieldName": "x-amz-bedrock-kb-source-uri"},

                            ]
                        }
                    }
                    
                },
                "type": "BEDROCK_RERANKING_MODEL"
            }

            
        }
    }

    if curso_impartido:
        config["vectorSearchConfiguration"]["filter"] = {
            "equals": {
                "key": "curso_impartido",
                "value": curso_impartido
            }
        }

    return config

from langchain.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda




REFORMULATE_WITH_HISTORY_MIU_PROMPT = PromptTemplate.from_template("""
Actúa como un reformulador de preguntas para un asistente académico especializado en los documentos de un curso impartido en la plataforma MiU de la Universidad Francisco Marroquín (UFM).
...

Historial del chat:
{history}

Última pregunta o input del usuario:
{question}

Pregunta reformulada:
""")


# Cadena de reformulación (usa el mismo modelo principal)
reformulate_chain = REFORMULATE_WITH_HISTORY_MIU_PROMPT | model | StrOutputParser()





def build_cimps_chain(curso_impartido: str | int ):

    curso_impartido = str(curso_impartido)  # aseguramos string

    retriever = AmazonKnowledgeBasesRetriever(
        region_name="us-west-2",
        knowledge_base_id=BASE_CONOCIMIENTOS_CIMPS,
        retrieval_config=generar_configuracion_retriever(curso_impartido)
    )

    filtered_retriever = retriever | RunnableLambda(limpiar_metadata_retrieved)


    prompt_template = create_prompt_template_procesos()

    chain = (
        RunnableParallel({
            "context": itemgetter("question") | filtered_retriever,
            "question": itemgetter("question"),
            "historial": itemgetter("historial"),
        })
        .assign(response=prompt_template | model | StrOutputParser())
        .pick(["response", "context"])
    )

    return chain

def run_cimps_chain(question, history, curso_impartido):
    chain = build_cimps_chain(curso_impartido)

        
    reformulated_question = reformulate_chain.invoke({
    "question": question,
    "history": history  
    })


    

    inputs = {
        "question": reformulated_question,
        "historial": history
    }

    return chain.stream(inputs)



def generate_name(prompt):
    try:
        input_text = (
            "Eres el asistente de documentos de MiU para un curso impartido "

            f"Texto base: {prompt}"
        )
        response = modelNames.invoke(input_text)
        return response.content.strip()
    except Exception as e:
        return "Consulta general de documentos del curso"



