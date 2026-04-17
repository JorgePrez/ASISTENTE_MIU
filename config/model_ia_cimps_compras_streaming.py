from langchain_aws import AmazonKnowledgeBasesRetriever, ChatBedrockConverse
from langchain_core.runnables import RunnableLambda
from typing import List, Dict, Any
from pydantic import BaseModel
import boto3
import requests
import re
from urllib.parse import urlparse


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


IS_TESTING = False

models = get_models_for_chatbots(app="MIU", is_testing=IS_TESTING)

model_id_chat = models["CHAT"]
model_id_rename = models["RENAME"]

session = boto3.Session(profile_name="testing" if IS_TESTING else None)

sts = session.client("sts")
identity = sts.get_caller_identity()
#print(f"🔝 Ejecutando como: {identity['Arn']}")
#print(f"🧾 Cuenta AWS: {identity['Account']}")

bedrock_runtime = session.client(
    service_name="bedrock-runtime",
    region_name="us-east-1"
)

model = ChatBedrockConverse(
    client=bedrock_runtime,
    model_id=model_id_chat,
    max_tokens=4096,
    temperature=0.0,
    additional_model_request_fields={
        "top_k": 250
    },
    provider="anthropic",
    disable_streaming=False,
)

modelNames = ChatBedrockConverse(
    client=bedrock_runtime,
    model_id=model_id_rename,
    max_tokens=256,
    temperature=0.0,
    additional_model_request_fields={
        "top_k": 250
    },
    provider="anthropic"
)


def _extraer_nombre_archivo(uri: str) -> str:
    if not uri:
        return ""

    p = urlparse(uri)
    path = p.path if p.scheme else uri
    path = path.rstrip("/")
    filename = path.split("/")[-1] if path else ""

    filename = re.sub(r"^miuDocumento_\d+_", "", filename)

    return filename


###########################################
# PROMPTS FIJOS PARA PODER CACHEAR MEJOR
###########################################

SYSTEM_PROMPT_ASISTENTE_CIMPS_FIJO = """
Tu conocimiento está estrictamente limitado al contenido presente en el `context`, el cual contiene los materiales oficiales subidos por el catedrático al curso impartido. Estos materiales pueden incluir guías, presentaciones, documentos PDF, lecturas asignadas, cronogramas, instrucciones de tareas, entre otros.

## Reglas clave:
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

## **Regla general:**  
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
"""

REFORMULATE_WITH_HISTORY_MIU_PROMPT_FIJO = """
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
"""

GENERATE_NAME_PROMPT_FIJO = """
Eres el asistente de documentos de MiU para un curso impartido de la Universidad Francisco Marroquín (UFM).
A partir del siguiente texto, genera únicamente un título breve (máximo 50 caracteres, en español) adecuado para nombrar una conversación.
El título debe ser educativo, respetuoso y apropiado para un entorno universitario.
Evita completamente lenguaje ofensivo, burlas, juicios de valor negativos, insinuaciones violentas o términos discriminatorios hacia personas, instituciones o autores.
No incluyas insultos, groserías, sarcasmo ni referencias provocadoras.
En su lugar, reformula de manera informativa, neutral o académica.
Entrega solo el título, sin comillas ni explicaciones.
"""


def limpiar_metadata_retrieved(docs):
    for doc in docs:
        for clave in [
            "x-amz-bedrock-kb-data-source-id",
            "x-amz-bedrock-kb-source-uri",
            "x-amz-bedrock-kb-document-page-number",
            "location",
            "type",
            "score",
        ]:
            doc.metadata.pop(clave, None)

        sm = doc.metadata.get("source_metadata")
        if isinstance(sm, dict):
            nombre_original = sm.get("nombre_archivo_original")
            if nombre_original:
                sm["nombre_archivo"] = nombre_original
            else:
                sm["nombre_archivo"] = _extraer_nombre_archivo(
                    sm.get("x-amz-bedrock-kb-source-uri", "")
                )

            for clave in [
                "referencia_chatbot",
                "nombre_archivo_original",
                "x-amz-bedrock-kb-data-source-id",
                "miu_documentos",
                "x-amz-bedrock-kb-document-page-number",
                "curso_impartido",
                "x-amz-bedrock-kb-source-uri",
            ]:
                sm.pop(clave, None)

    return docs


BASE_CONOCIMIENTOS_CIMPS = "UALUBVCZO1"


def generar_configuracion_retriever(curso_impartido: str) -> dict:
    config = {
        "vectorSearchConfiguration": {
            "numberOfResults": 100,
            "rerankingConfiguration": {
                "bedrockRerankingConfiguration": {
                    "modelConfiguration": {
                        "modelArn": "arn:aws:bedrock:us-east-1::foundation-model/cohere.rerank-v3-5:0",
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


def history_to_text(history: Any) -> str:
    if not history:
        return ""

    lines = []

    for msg in history:
        if isinstance(msg, dict):
            role = msg.get("role", "user")
            content = msg.get("content", "")
        else:
            role = getattr(msg, "type", "user")
            content = getattr(msg, "content", "")

        lines.append(f"{role}: {content}")

    return "\n".join(lines)


def normalize_history_for_converse(history: Any) -> list:
    if not history:
        return []

    normalized = []

    for msg in history:
        if isinstance(msg, dict):
            role = msg.get("role", "user")
            content = msg.get("content", "")
        else:
            role = getattr(msg, "type", "user")
            content = getattr(msg, "content", "")

        if role not in ["user", "assistant"]:
            role = "user"

        normalized.append((role, content))

    return normalized


def docs_to_context(docs) -> str:
    bloques = []

    for i, doc in enumerate(docs, start=1):
        bloques.append(f"[Fragmento {i}]")
        bloques.append(doc.page_content)

        if doc.metadata:
            bloques.append(f"Metadata: {doc.metadata}")

        bloques.append("")

    return "\n".join(bloques)


def get_text_from_response(response) -> str:
    text_attr = getattr(response, "text", None)

    if isinstance(text_attr, str) and text_attr.strip():
        return text_attr.strip()

    content = getattr(response, "content", None)

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        partes = []

        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    partes.append(text)
            else:
                text = getattr(item, "text", None)
                if isinstance(text, str) and text.strip():
                    partes.append(text)

        if partes:
            return "\n".join(partes).strip()

    return str(response).strip()


def get_text_from_chunk(chunk) -> str:
    text_attr = getattr(chunk, "text", None)

    if isinstance(text_attr, str):
        return text_attr

    content = getattr(chunk, "content", None)

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        partes = []

        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    partes.append(text)
            else:
                text = getattr(item, "text", None)
                if isinstance(text, str):
                    partes.append(text)

        return "".join(partes)

    return ""


def reformulate_question(question, history):
    history_text = history_to_text(history)

    messages = [
        (
            "human",
            [
                {"type": "text", "text": REFORMULATE_WITH_HISTORY_MIU_PROMPT_FIJO},
                {"cachePoint": {"type": "default", "ttl": "1h"}},
                {
                    "type": "text",
                    "text": (
                        f"Historial del chat:\n{history_text}\n\n"
                        f"Última pregunta o input del usuario:\n{question}\n\n"
                        "Pregunta reformulada:"
                    ),
                },
            ],
        )
    ]

    response = model.invoke(messages)
    return get_text_from_response(response)


def stream_cimps_model(question, history, docs):
    context_text = docs_to_context(docs)
    normalized_history = normalize_history_for_converse(history)

    messages = [
        (
            "system",
            [
                {"type": "text", "text": SYSTEM_PROMPT_ASISTENTE_CIMPS_FIJO},
                {"cachePoint": {"type": "default", "ttl": "1h"}},
                {
                    "type": "text",
                    "text": f"Base de conocimientos recuperada:\n\n{context_text}",
                },
            ],
        )
    ]

    messages.extend(normalized_history)
    messages.append(("human", question))

    last_usage_metadata = None

    for chunk in model.stream(messages):
        chunk_text = get_text_from_chunk(chunk)
        chunk_usage = getattr(chunk, "usage_metadata", None)

        if chunk_usage:
            last_usage_metadata = chunk_usage

        if chunk_text:
            yield {
                "response": chunk_text,
                "usage_metadata": None,
            }

    yield {
        "response": "",
        "usage_metadata": last_usage_metadata,
    }


def build_cimps_chain(curso_impartido: str | int):
    curso_impartido = str(curso_impartido)

    retriever = AmazonKnowledgeBasesRetriever(
        region_name="us-east-1",
        knowledge_base_id=BASE_CONOCIMIENTOS_CIMPS,
        retrieval_config=generar_configuracion_retriever(curso_impartido),
    )

    filtered_retriever = retriever | RunnableLambda(limpiar_metadata_retrieved)

    return {
        "retriever": filtered_retriever
    }


def run_cimps_chain(question, history, curso_impartido):
    chain_parts = build_cimps_chain(curso_impartido)
    retriever = chain_parts["retriever"]

    reformulated_question = reformulate_question(question, history)
    docs = retriever.invoke(reformulated_question)

    #print("\n==============================")
    #print(" Pregunta original del usuario:")
    #print(question)
    #print("------------------------------")
    #print(" Pregunta reformulada:")
    #print(reformulated_question)
    #print("==============================\n")

    final_usage_metadata = None

    for chunk in stream_cimps_model(
        question=reformulated_question,
        history=history,
        docs=docs,
    ):
        if chunk.get("usage_metadata"):
            final_usage_metadata = chunk["usage_metadata"]
            print("PROMPT PRINCIPAL ASISTENTE MIU USAGE METADATA:", final_usage_metadata)


        yield {
            "response": chunk.get("response", ""),
            "context": docs,
            "usage_metadata": final_usage_metadata,
            "reformulated_question": reformulated_question,
        }


def generate_name(prompt):
    try:
        messages = [
            (
                "human",
                [
                    {"type": "text", "text": GENERATE_NAME_PROMPT_FIJO},
                    {"cachePoint": {"type": "default", "ttl": "1h"}},
                    {
                        "type": "text",
                        "text": f"Consulta:\n{prompt}\n\nTítulo:",
                    },
                ],
            )
        ]

        response = modelNames.invoke(messages)
        return get_text_from_response(response)

    except Exception:
        return "Consulta general de documentos del curso"


# --------------------------
# Modelo para citar documentos recuperados

class Citation(BaseModel):
    page_content: str
    metadata: Dict


def extract_citations(response: List[Dict]) -> List[Citation]:
    return [Citation(page_content=doc.page_content, metadata=doc.metadata) for doc in response]
# --------------------------