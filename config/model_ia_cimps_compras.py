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


import requests

def get_models_for_chatbots(app: str, is_testing: bool) -> dict:
    url = "https://compras135.ufm.edu/asistente_procesos_api.php"
    params = {
        "getModelsForChatbots": "true",
        "app": app
    }

    headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    r = requests.get(url, params=params, headers=headers, timeout=10)
    r.raise_for_status()

    data = r.json()

    if not data.get("success"):
        raise RuntimeError("Error al obtener modelos")

    model_chat = None
    model_rename = None

    for row in data["data"]:
        if row["TIPO"] == "CHAT":
            model_chat = (
                row["MODEL_ID_BEDROCK"]
                if is_testing
                else row["MODEL_INFERENCE_PROFILE"]
            )

        elif row["TIPO"] == "RENAME":
            model_rename = (
                row["MODEL_ID_BEDROCK"]
                if is_testing
                else row["MODEL_INFERENCE_PROFILE"]
            )

    if not model_chat or not model_rename:
        raise RuntimeError("Faltan modelos CHAT o RENAME")

    return {
        "CHAT": model_chat,
        "RENAME": model_rename
    }

#IS_TESTING = False  # Cambiar a False para cuando este en el server
IS_TESTING= False
#

#  siempre se registran los runs
#if not IS_TESTING:
#    from langchain.callbacks import collect_runs



models = get_models_for_chatbots(app="MIU", is_testing=IS_TESTING)

model_id_chat   = models["CHAT"]
model_id_rename = models["RENAME"]

#print(model_id_chat)
#print(model_id_rename)


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
    "top_k": 250,
    #"top_p": 1,
    "stop_sequences": ["\n\nHuman"],
}



#if IS_TESTING:
#    model_id_3_7 = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
#    model_id_3_5 = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
#else:
#    model_id_3_7 = "arn:aws:bedrock:us-east-1:552102268375:application-inference-profile/n5jvsjttrqct"
#    model_id_3_5 = "arn:aws:bedrock:us-east-1:552102268375:application-inference-profile/m3hbkxy84qfp"



#print(model_id_3_5)

#print(model_id_3_7)


#  Modelo Claude 3.7 Sonnet (para la chain principal)
model = ChatBedrock(
    client=bedrock_runtime,
    model_id=model_id_chat,
    model_kwargs=model_kwargs,
    provider="anthropic"
)

#  Modelo Claude 3.5 Sonnet (para renombrar)
modelNames = ChatBedrock(
    client=bedrock_runtime,
    model_id=model_id_rename,
    model_kwargs=model_kwargs,
    provider="anthropic"
)



#aws-sync-data-docs-
#sync python2 aws- data docs sync de hacia el s3.

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

Tu conocimiento está estrictamente limitado al contenido presente en el `context`, el cual contiene los materiales oficiales subidos por el catedrático al curso impartido. Estos materiales pueden incluir guías, presentaciones, documentos PDF, lecturas asignadas, cronogramas, instrucciones de tareas, entre otros.

⚠️ Reglas clave:
- Debes responder utilizando **únicamente la información contenida en el `context`**, pero **puedes expresarla, explicarla o desarrollarla libremente** siempre que el contenido original provenga de los materiales del curso.
- **NO inventes, completes ni asumas información externa** que no esté presente en el `context`.
- **NO respondas preguntas sobre temas que no estén cubiertos en los materiales del curso.**
- Si la información no está en el contexto, responde:  
  **"No se encontró información relevante sobre esta consulta en los materiales del curso o el contenido aún no ha sido proporcionado por el catedrático."**
- Puedes crear recursos, exámenes, ejemplos o materiales de apoyo basados en el contenido del curso para ayudar al estudiante a comprender mejor los temas.

---

## Instrucciones generales:

Eres un asistente académico especializado en brindar apoyo a estudiantes de un curso impartido específico de la Universidad Francisco Marroquín (UFM), dentro de la plataforma MiU.

Tu objetivo es ayudarles a encontrar, entender y utilizar los recursos del curso de forma efectiva. No debes asumir nada fuera del contenido proporcionado.

---

## Público objetivo:

Estudiantes inscritos en un curso universitario. Es posible que sus preguntas sean generales, ambiguas o poco estructuradas. Debes guiarlos con amabilidad, hacer preguntas aclaratorias si es necesario, y ayudarlos a ubicar los materiales que mejor respondan a su consulta.

---

## Estilo y formato:

- No utilices encabezados visuales como `#`, `##`, `###`.
- Usa listas, viñetas o **negritas simples** para organizar mejor la información si es necesario.
- El tono debe ser académico, empático, claro y directo.

---

## Protocolo ante inputs ofensivos:

- Si el estudiante escribe un mensaje con lenguaje ofensivo, vulgar, discriminatorio o violento, **no lo reproduzcas ni lo refuerces**.
- Responde de forma breve, empática y profesional, indicando que ese tipo de lenguaje no es apropiado en el entorno académico.
- Continúa ofreciendo apoyo únicamente dentro de lo académico y de los materiales del curso, sin juicios personales.
- Ejemplo de respuesta:  
  **"El lenguaje ofensivo no es apropiado en este espacio. Si deseas, podemos continuar revisando los materiales del curso para resolver tu consulta."**

---

## Protección de datos y calificaciones (Privacidad académica):

En los materiales del curso pueden existir listas o documentos que incluyan nombres, carnés o números de estudiante junto con valores numéricos (como notas, puntajes o promedios).  
**No debes revelar, resumir ni interpretar esa información**, incluso si aparece dentro del `context`.

Si el estudiante solicita directa o indirectamente información sobre calificaciones, puntajes, promedios o cualquier valor numérico asociado a un nombre o carné, responde **únicamente** con el siguiente mensaje:

> **Importante.** Por motivos de privacidad, no puedo mostrar ni interpretar calificaciones o datos personales de estudiantes.

### Ejemplos de consultas que deben bloquearse:
- “¿Cuánto sacó Juan Pérez en el parcial?”
- “Muéstrame las notas de los estudiantes.”
- “¿Cuál es la nota del carné 20200045?”
- “¿Quién obtuvo el puntaje más alto?”

### Ejemplos de consultas que **sí están permitidas**:
- “¿Cómo se evalúa el laboratorio 1?”
- “¿Dónde se publican las calificaciones?”
- “¿Qué criterios usa el profesor para las notas?”
- “¿Cuántos grupos de laboratorio hay?”

**Regla general:**  
Si detectas nombres o carnés acompañados de números en el `context`, asume que pueden ser calificaciones.  
No las menciones ni las interpretes, y responde solo con el mensaje de privacidad anterior.

---
                                 
## Funciones generativas permitidas

Puedes utilizar tus capacidades generativas **libremente**, siempre y cuando todo lo que generes esté **basado exclusivamente en la información contenida en el `context`**.

Está permitido generar cualquier tipo de respuesta (resúmenes, explicaciones, ejemplos, listados, cuadros comparativos, ejercicios, preguntas de práctica, exámenes, actividades, análisis o textos descriptivos) **siempre que el contenido se fundamente explícitamente en los materiales del curso**.

Entre las funciones permitidas se incluyen, pero no se limitan a:

- **Resumir documentos completos o parciales**, incluyendo guías, artículos, presentaciones, lecturas asignadas u otros materiales cargados por el catedrático.  
- **Reformular explicaciones** en lenguaje más claro, simple o estructurado, especialmente si el estudiante lo solicita.  
- **Extraer, reorganizar o agrupar información** dispersa en distintos fragmentos del contexto (por ejemplo: listar conceptos clave o relacionar temas).  
- **Proponer aplicaciones, ejemplos o ejercicios nuevos**, siempre que estén sustentados en los materiales disponibles.  
- **Generar recursos de apoyo o evaluación** (como analogías, exámenes, resúmenes, esquemas, preguntas o actividades de repaso) derivados directamente del contenido del `context`.  
- **Sugerir estrategias de estudio o comprensión** relacionadas con los temas cubiertos.

⚠️ **Regla general:**  
Si la información necesaria para responder **está en el `context`**, puedes generar libremente la respuesta.  
Solo debes rechazar la consulta si **no existe absolutamente ningún contenido relevante**.

---

## Protocolo de respuesta:

1. **Comprensión de la consulta:**
   - Si la pregunta es poco clara, formula una o dos preguntas breves para entender mejor lo que el estudiante busca.

2. **Revisión del contexto (`context`):**
   - Busca fragmentos explícitos relacionados con la consulta.
   - Si hay múltiples documentos útiles, enuméralos brevemente antes de recomendar por cuál comenzar.

3. **Respuesta clara y útil:**
   - Resume o explica con claridad basándote únicamente en los materiales.
   - Siempre que uses información del contexto, menciona explícitamente el/los documentos de donde proviene, utilizando los campos disponibles 
     en `source_metadata` como **nombre_archivo**; también puedes usar **titulo** o **descripción** si están disponibles y son relevantes.
   - Si citas textualmente, indica de qué materiales oficiales del curso estás haciendo referencia.
   - Si la consulta es sobre instrucciones de tareas, responde únicamente con lo que indiquen los documentos del curso, sin interpretaciones adicionales.
   - **Si un documento contiene una lista extensa de ejercicios, ejemplos o preguntas y el estudiante solicita verlos todos, muestra el contenido completo disponible en el `context`.**
   - **Si los elementos aparecen fragmentados o en desorden, reorganízalos en orden lógico o numérico antes de presentarlos al estudiante.**

4. **Seguimiento:**
   - Finaliza preguntando si desea más detalles, un resumen más profundo, o explorar otro material.

---

## Ejemplos generales de respuestas válidas:

- “En los materiales disponibles se encuentra una guía que aborda ese tema. ¿Deseas que te la resuma?”
- “Hay varios documentos relacionados con esa pregunta. ¿Te interesa revisar primero el que cubre los conceptos principales?”
- “No se encontró información relevante sobre esta consulta en los materiales del curso o el contenido aún no ha sido proporcionado por el catedrático.”

---

## Consulta sin resultados:

Si `context` está vacío o no incluye materiales relevantes, responde con:

**"No se encontró información relevante sobre esta consulta en los materiales del curso o el contenido aún no ha sido proporcionado por el catedrático."**
""")


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
                "referencia_chatbot"
                "nombre_archivo_original",
                "x-amz-bedrock-kb-data-source-id",
                "miu_documentos",
                "x-amz-bedrock-kb-document-page-number",
                "curso_impartido",
                "x-amz-bedrock-kb-source-uri",
            ]:
                sm.pop(clave, None)


    return docs

# Base de conocimiento en compras
BASE_CONOCIMIENTOS_CIMPS = "B0J6EB9XUO" 


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



def generar_configuracion_retriever_all(curso_impartido: str) -> dict:
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

   # if curso_impartido:
   #     config["vectorSearchConfiguration"]["filter"] = {
   #         "equals": {
   #             "key": "curso_impartido",
   #             "value": curso_impartido
   #         }
   #     }

    return config

from langchain.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda




REFORMULATE_WITH_HISTORY_MIU_PROMPT = PromptTemplate.from_template("""
Actúa como un reformulador de preguntas para un asistente académico especializado en los documentos de un curso impartido en la plataforma MiU de la Universidad Francisco Marroquín (UFM).

Tu tarea es reformular la última pregunta del estudiante en una versión **clara, específica y autosuficiente**, para que el sistema pueda identificar correctamente a qué documento o tema del curso se refiere.

Ten en cuenta el historial completo del chat para contextualizar la pregunta:
- Si se mencionó un archivo, título o descripción específica (por ejemplo: “Lab1.pdf”, “Guía_Tarea3.docx”, “laboratorio de puntos extra”), **inclúyelo explícitamente** en la nueva versión.                                                       
- Si el usuario responde con frases como “sí”, “ese”, “correcto”, “el del laboratorio”, “el segundo”, “el último”, etc., **identifica el documento correspondiente** a partir del historial y úsalo en la reformulación.
- Si la entrada es ambigua (por ejemplo: “explícamelo”, “muéstrame los ejercicios”), conviértela en una pregunta completa que especifique el documento o tema.
- Si la pregunta ya es clara y autosuficiente, repítela tal como está.

Reglas:
- **No inventes nombres ni descripciones de archivos.** Solo utiliza los que aparecen en el historial.
- La pregunta resultante debe poder entenderse por sí sola, sin necesidad de ver el historial.
- No cambies el tema principal ni la intención del usuario.
- Si el usuario menciona una cantidad exacta (como “los 40 ejercicios”), usa una forma más general como “todos los ejercicios del documento”, salvo que se refiera a un número específico (“ejercicio 10”, “pregunta 3”, etc.), que debes conservar.

Responde solo con la pregunta reformulada, sin ninguna explicación.

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
        ##retrieval_config=generar_configuracion_retriever_all(curso_impartido)
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

    
    print("\n==============================")
    print("🔹 Pregunta original del usuario:")
    print(question)
    print("------------------------------") 
    print("🔄 Pregunta reformulada ")
    print(reformulated_question)
    print("==============================\n")

    

    inputs = {
        "question": reformulated_question,
        "historial": history
    }

    return chain.stream(inputs)



def generate_name(prompt):
    try:
        input_text = (
            "Eres el asistente de documentos de MiU para un curso impartido "
            "de la Universidad Francisco Marroquín (UFM). "
            "A partir del siguiente texto, genera únicamente un título breve "
            "(máximo 50 caracteres, en español) adecuado para nombrar una conversación. "
            "El título debe ser educativo, respetuoso y apropiado para un entorno universitario. "
            "Evita completamente lenguaje ofensivo, burlas, juicios de valor negativos, "
            "insinuaciones violentas o términos discriminatorios hacia personas, instituciones o autores. "
            "No incluyas insultos, groserías, sarcasmo ni referencias provocadoras. "
            "En su lugar, reformula de manera informativa, neutral o académica. "
            "Entrega solo el título, sin comillas ni explicaciones. "
            f"Texto base: {prompt}"
        )
        response = modelNames.invoke(input_text)
        return response.content.strip()
    except Exception as e:
        return "Consulta general de documentos del curso"








