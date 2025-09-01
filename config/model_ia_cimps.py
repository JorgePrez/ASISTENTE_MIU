

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



IS_TESTING = True  # Cambiar a False para producción


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
        region_name="us-east-1",
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
    model_id_3_7 = "arn:aws:bedrock:us-east-1:552102268375:application-inference-profile/hkqiiam51emk"
    model_id_3_5 = "arn:aws:bedrock:us-east-1:552102268375:application-inference-profile/yg7ijraub0q5"



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

Tu conocimiento está estrictamente limitado al contenido presente en el `context`, el cual contiene los materiales oficiales subidos por el catedrático al curso impartido. Estos materiales pueden incluir guías, presentaciones, documentos PDF, lecturas asignadas, cronogramas, instrucciones de tareas, entre otros.

⚠️ Reglas clave:
- Solo puedes responder utilizando la información que se encuentra explícitamente dentro del `context`.
- **NO inventes, completes ni asumas información** que no esté presente en el `context`.
- **NO respondas preguntas sobre temas que no estén cubiertos en los materiales del curso.**
- Si la información no está en el contexto, responde:  
  **"No se encontró información relevante sobre esta consulta en los materiales del curso o el contenido aún no ha sido proporcionado por el catedrático."**
- Tu función no es reemplazar al profesor ni evaluar tareas, únicamente guiar al estudiante dentro de los materiales proporcionados.

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
                                 
## Funciones generativas permitidas

Puedes utilizar tus capacidades generativas **únicamente a partir del contenido presente en el `context`**. Está permitido generar explicaciones, ejemplos o ayudas nuevas **siempre y cuando estén claramente fundamentadas en los materiales proporcionados**.

Entre las funciones permitidas se incluyen:

- **Resumir documentos completos o parciales**, incluyendo guías, artículos, presentaciones, lecturas asignadas u otros materiales cargados por el catedrático.
- **Reformular explicaciones** en lenguaje más claro, simple o estructurado, especialmente si el estudiante lo solicita.
- **Extraer, reorganizar o agrupar información** dispersa en distintos fragmentos del contexto (por ejemplo: listar todos los conceptos clave mencionados en un documento).
- **Proponer formas de reutilizar, aplicar o combinar contenido existente**, como relacionar ejemplos, resumenes, ejercicios, definiciones o criterios ya presentes en los documentos.
- **Generar ideas, explicaciones adicionales o recursos de apoyo** (como analogías, resumenes o posibles preguntas de práctica), siempre que se basen de forma explícita en el contenido disponible.
- **Sugerir estrategias de estudio o comprensión** relacionadas con los temas cubiertos en los materiales.

⚠️ **No debes inventar información fuera del `context`**  
No generes conceptos, explicaciones o respuestas que no estén fundamentadas en los materiales del curso. Tu función es facilitar el acceso, la comprensión y el aprovechamiento de lo que ya ha sido proporcionado por el catedrático.
               
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
     en `source_metadata` como **nombre_archivo** también puedes usar **titulo** o **descripción** si estan disponibles y son relevantes
   - Si citas textualmente, limita la cita a una o dos frases e indica que provienen de los materiales oficiales del curso.
   - Si la consulta es sobre instrucciones de tareas, responde únicamente con lo que indiquen los documentos del curso, sin interpretaciones adicionales.
                                 
3. **Respuesta clara y útil:**
   - Resume o explica con claridad basándote únicamente en los materiales.
   - Siempre que uses información del contexto, menciona explícitamente el/los documentos de donde proviene, utilizando los campos disponibles 
     en `source_metadata` como **nombre_archivo**; también puedes usar **titulo** o **descripción** si están disponibles y son relevantes.
   - Si citas textualmente, indica de que  materiales oficiales del curso estas haciendo referencia.
   - Si la consulta es sobre instrucciones de tareas, responde únicamente con lo que indiquen los documentos del curso, sin interpretaciones adicionales.
   - **Si un documento contiene una lista extensa de ejercicios, ejemplos, preguntas u otros elementos similares, y el estudiante solicita verlos todos, muestra el contenido completo disponible en el `context`, sin rechazar la solicitud por razones de cantidad.**
   - **Si los elementos aparecen fragmentados o en desorden (por ejemplo: ejercicios divididos en varios fragmentos), reorganízalos en orden lógico o numérico antes de presentarlos al estudiante, siempre que la numeración o secuencia esté disponible en el contexto.**

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
        if "source_metadata" in doc.metadata:
            sm = doc.metadata["source_metadata"]
            # Siempre viene, así que extraemos directo
            sm["nombre_archivo"] = _extraer_nombre_archivo(sm["x-amz-bedrock-kb-source-uri"])


            for clave in [
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


# config = {
#        "vectorSearchConfiguration": {
#            "numberOfResults": 100,
#            "rerankingConfiguration": {
#                "bedrockRerankingConfiguration": {
#                    "modelConfiguration": {
#                        "modelArn": "arn:aws:bedrock:us-west-2::foundation-model/cohere.rerank-v3-5:0",
#                    },
#                    "numberOfRerankedResults": 30,
#                    "metadataConfiguration": {
#                        "selectionMode": "SELECTIVE",
#                        "selectiveModeConfiguration": {
#                            "fieldsToInclude": [
#                                {"fieldName": "titulo"},
#                                {"fieldName": "descripcion"}
#                            ]
#                        }
#                    }
                    
#                },
#                "type": "BEDROCK_RERANKING_MODEL"
#            }

            
#        }
#    }



#x-amz-bedrock-kb-source-uri

  
#                              "fieldsToInclude": [
#                                {"fieldName": "titulo"},
#                                {"fieldName": "descripcion"}
#                            ]


def generar_configuracion_retriever(curso_impartido: str) -> dict:
    config = {
        "vectorSearchConfiguration": {
            "numberOfResults": 100,
            "rerankingConfiguration": {
                "bedrockRerankingConfiguration": {
                    "modelConfiguration": {
                        "modelArn": "arn:aws:bedrock:us-west-2::foundation-model/cohere.rerank-v3-5:0",
                    },
                    "numberOfRerankedResults": 25,
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

Tu tarea es transformar la última pregunta del estudiante en una versión clara, autosuficiente y específica, adecuada para buscar en una base de conocimientos formada por materiales académicos. Estos materiales incluyen documentos PDF, archivos Word, guías, laboratorios, tareas, presentaciones y otros archivos subidos por el catedrático al curso.

Toma en cuenta el historial completo del chat para hacer la reformulación más precisa:
- Si anteriormente se mencionó un archivo específico (por ejemplo: “Lab1.pdf”, “Guía_Tarea3.docx”, “laboratorio de puntos extra”), incorpora el **nombre del archivo, título o descripción** ya mencionado en la reformulación.                                                       
- Si el usuario responde con “sí”, “ese”, “correcto”, “el del laboratorio”, “el segundo archivo”, “el último”, etc., **identifica el documento al que se refiere con base en el historial** y úsalo explícitamente en la nueva pregunta.
- Si el input original es ambiguo (por ejemplo: “explícamelo”, “muéstrame los ejercicios”), conviértelo en una consulta completa que especifique a qué documento se refiere.
- Si la pregunta ya es clara y autosuficiente, repítela tal como está.

Reglas adicionales:
- No inventes nombres de archivos, títulos ni descripciones. Solo incluye referencias documentales si ya han sido mencionadas en la conversación.
- Reformula de forma que la pregunta resultante pueda ser entendida por sí sola, sin necesidad de ver el historial anterior.
- No alteres el tema principal de la consulta del usuario.
- Si el usuario menciona una **cantidad total exacta** (como “los 40 ejercicios”, “las 5 preguntas”), reformula la pregunta de forma **más flexible**: omite la cantidad específica y usa expresiones como **“todos los ejercicios disponibles”** o **“los ejercicios que aparecen en el documento”**. Esto evita errores si la cantidad exacta no puede ser confirmada de forma explícita en el contexto.
- Esta regla **no aplica** si el número hace referencia a un ítem individual específico, como por ejemplo: “el ejercicio número 10”, “la pregunta 3”, “el punto 18”, etc. En esos casos, **mantén la referencia numérica exacta**.

- Si el usuario solicita una **actividad generativa basada en el contenido** (por ejemplo: “hazme un quiz”, “genera preguntas de práctica”, “resume el texto con tus palabras”), reformula la pregunta para indicar que se desea **crear un recurso de apoyo basado en un documento específico ya mencionado**. Usa expresiones como:
  - “En base al documento [nombre_archivo], genera un cuestionario de práctica para estudiar.”
  - “A partir del documento mencionado, elabora un resumen  para facilitar su comprensión.”
                                                                   
- Evita usar expresiones como “resueltas”, “solucionadas”, “contestadas” o similares. Prefiere expresiones neutrales como “para practicar”, “para repasar” o “como referencia”.
- Si el usuario utiliza verbos como “crear”, “inventar”, “hacer”, “formular”, “construir”, “elaborar”, etc., reformula usando el verbo **“generar”** para mantener consistencia con las funciones generativas permitidas por el asistente.
                                                                   

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








