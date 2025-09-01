import streamlit as st
import config.dynamo_crud as DynamoDatabase
import uuid
from config.model_ia_cimps import run_cimps_chain 
import requests

from dotenv import load_dotenv
from langsmith import traceable
from langsmith import Client

#from streamlit_feedback import streamlit_feedback

from langsmith.run_helpers import get_current_run_tree

from streamlit_feedback import streamlit_feedback

from langchain.callbacks import collect_runs


from streamlit.components.v1 import html

import streamlit.components.v1 as components

import base64
import json

# Obtener token de query params

st.set_page_config(layout="wide")

st.markdown("<div style='height: 50px;'></div>", unsafe_allow_html=True)
st.sidebar.markdown("<div style='height: 50px;'></div>", unsafe_allow_html=True)




# Cargar variables de entorno
load_dotenv()
client = Client()

import os
# Healthcheck endpoint simulado
if st.query_params.get("check") == "1":
    st.markdown("OK")
    st.stop()




st.markdown("""
    <style>
            
    [data-testid="stSidebarHeader"] {
            display: none !important;
        }
            
    [data-testid="stSidebarHeader"] {
            visibility: hidden !important;
            height: 0 !important;
            padding: 0 !important;
        }
            
    [data-testid="stSidebar"] {
            width: 400px !important;
            flex-shrink: 0 !important;
        }
            
    
    div.block-container {
        padding-top: 0rem !important;
    }
            

    
    
    /*-30px*/
            
   
    /*        
     div.st-key-chat_input_miu textarea[data-testid="stChatInputTextArea"] {
        border: 1.5px solid #d60812 !important;
        border-radius: 10px !important;
        padding: 0.5rem !important;
        background-color: white !important;
    }   
    */
            
    div.st-key-chat_input_miu::after {
        content: "";
        display: block;
        text-align: center;
        font-size: 0.75rem;
        color: #999;
        margin-top: 8px;
    }
            
            
                    
div.st-key-mensaje_nuevo_chat_sidebarOLD button {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 0.5rem !important;
    padding: 0.4rem 1rem !important;
    margin: 0 auto !important;
    width: auto !important;
    white-space: nowrap !important;
    font-weight: bold;
    border-radius: 8px !important;
    text-align: center !important;
}
            
div.st-key-mensaje_nuevo_chat_sidebar button {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 0.5rem !important;
    padding: 0.4rem 1rem !important;
    margin: 0 auto !important;
    min-width: 220px !important;  /* Aumenta el ancho mínimo */
    max-width: 75% !important;   /* Para que no se salga de su contenedor */
    white-space: nowrap !important;
    font-weight: bold;
    border-radius: 8px !important;
    text-align: center !important;
    transition: all 0.2s ease-in-out;
}
            


                      
div.st-key-mensaje_nuevo_chat_sidebar button:hover {
    background-color: #d6081f !important;
    color: white !important;
}

            

/* Aplica a todos los botones de abrir conversación por patrón de key */
            

div[class^="st-key-id_"] button {
    min-width: 180px !important;
    text-align: left !important;  /* Opcional: alinear texto si es largo */
}

    </style>
""", unsafe_allow_html=True)



def invoke_with_retries_procesos(run_chain_fn, question, history, config=None, max_retries=10):
    attempt = 0
    warning_placeholder = st.empty()

    
    with st.chat_message("assistant"):
        response_placeholder = st.empty()

        while attempt < max_retries:
            try:
                print(f"Reintento {attempt + 1} de {max_retries}")
                full_response = ""

                for chunk in run_chain_fn(question, history):
                    if 'response' in chunk:
                        full_response += chunk['response']
                        response_placeholder.markdown(full_response)

                response_placeholder.markdown(full_response)

                st.session_state.messages_procesos.append({
                    "role": "assistant",
                    "content": full_response,
                })

                DynamoDatabase.edit(
                    st.session_state.chat_id_procesos,
                    st.session_state.messages_procesos,
                    st.session_state.username,
                    st.session_state.curso_impartido_id

                )

                if DynamoDatabase.getNameChat(st.session_state.chat_id_procesos, st.session_state.username, st.session_state.curso_impartido_id) == "nuevo chat":
                    DynamoDatabase.editName(st.session_state.chat_id_procesos, question, st.session_state.username, st.session_state.curso_impartido_id)
                    st.rerun()

                warning_placeholder.empty()
                return

            except Exception as e:
                attempt += 1
                if attempt == 1:
                    warning_placeholder.markdown("⌛ Esperando generación de respuesta...", unsafe_allow_html=True)
                print(f"Error inesperado en reintento {attempt}: {str(e)}")
                if attempt == max_retries:
                    warning_placeholder.markdown("⚠️ **No fue posible generar la respuesta, vuelve a intentar.**", unsafe_allow_html=True)


def main():


    token = st.query_params.get("token")


    if token:
        try:
            decoded = base64.b64decode(token).decode("utf-8")
            data = json.loads(decoded)
            st.session_state.username =session = data.get("user_id")
            st.session_state.persona_id = persona_id=  data.get("id_persona")
            st.session_state.curso_impartido_id = curso_impartido_id = data.get("curso_impartido_id")
            st.session_state.servidor =servidor = data.get("servidor")
            ts = data.get("ts")  # si lo usas

            print(curso_impartido_id)

        except Exception as e:
            st.error("⚠️ Acceso denegado")
            st.stop()

    else:
        st.error("⚠️ Acceso denegado.")
        st.stop()

    
    titulo = f"Asistente del curso impartido - {curso_impartido_id} 🤖"



    import requests


        # Obtener contexto desde la API
    url = "https://compras135.ufm.edu/asistente_procesos_api.php"
    params = {
            "buscarCursoNombre": "true",
            "curso_impartido": curso_impartido_id
        }

    headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }

    response = requests.get(url, params=params, headers=headers)
    

    if response.status_code == 200:
        evaluaciones_json = response.json()

        nombre_curso = evaluaciones_json.get("NOMBRE_CURSO", "")
        seccion = evaluaciones_json.get("SECCION", "")
        titulo = f"Asistente del curso: {nombre_curso} - Sección {seccion} 🤖 ({curso_impartido_id})"



    mensaje_nuevo_chat = "Nuevo chat"

   # st.subheader(titulo, divider='rainbow')

    st.markdown(f"""
<div style="display: flex; align-items: center; margin-bottom: 0;">
 <h4 style="margin: 0;">{titulo} </h4>
</div>
<hr style='border: 1px solid #d6081f; margin-top: 0; margin-bottom: 24px;'>
""", unsafe_allow_html=True)

    ## TODO: Obtener información del curso impartido
    ## TODO: Obtener información de los documentos del curso





    if "messages_procesos" not in st.session_state:
        st.session_state.messages_procesos = []
    if "chat_id_procesos" not in st.session_state:
        st.session_state.chat_id_procesos = ""
    if "new_chat_procesos" not in st.session_state:
        st.session_state.new_chat_procesos = False

    def cleanChat():
        st.session_state.new_chat_procesos = False

    def cleanMessages():
        st.session_state.messages_procesos = []

    def loadChat(chat, chat_id):
        st.session_state.new_chat_procesos = True
        st.session_state.messages_procesos = chat
        st.session_state.chat_id_procesos = chat_id

    with st.sidebar:

                
                # https://miu.ufm.edu/templates/default/images/miublanco3.png

        st.sidebar.markdown(f"""
            <div style="text-align: center; margin-bottom: 20px; margin-top: -25px;">
                <img src="https://intranet.ufm.edu/reportesai/img_chatbot/UFM-LOGO-MATOR.png  " 
                    style="width: 100%; max-width: 150px;">
            </div>
        """, unsafe_allow_html=True)



       #        if st.button(mensaje_nuevo_chat, key="mensaje_nuevo_chat_sidebar", icon=":material/add:", use_container_width=False):


        if st.button(mensaje_nuevo_chat, key="mensaje_nuevo_chat_sidebar", icon=":material/add:", use_container_width=True):
            st.session_state.chat_id_procesos = str(uuid.uuid4())
            DynamoDatabase.save(st.session_state.chat_id_procesos, session,curso_impartido_id ,  "nuevo chat", [])
            st.session_state.new_chat_procesos = True
            cleanMessages()
        
        st.markdown("""
        <hr style='border: none; height: 1px; background-color: #d6081f; margin: 8px 0 16px 0;'>
        """, unsafe_allow_html=True)

        datos = DynamoDatabase.getChats(session,  curso_impartido_id)

        if datos:
            for item in datos:
                chat_id = item["SK"].split("#")[1]
                if f"edit_mode_{chat_id}" not in st.session_state:
                    st.session_state[f"edit_mode_{chat_id}"] = False

                with st.container():
                    c1, c2, c3 = st.columns([8, 1, 1])

                    c1.button(f"  {item['Name']}", type="tertiary", key=f"id_{chat_id}", on_click=loadChat,
                              args=(item["Chat"], chat_id), use_container_width=True)

                    c2.button("", icon=":material/edit:", key=f"edit_btn_{chat_id}", type="tertiary", use_container_width=True,
                              on_click=lambda cid=chat_id: st.session_state.update(
                                  {f"edit_mode_{cid}": not st.session_state[f"edit_mode_{cid}"]}))

                    c3.button("", icon=":material/delete:", key=f"delete_{chat_id}", type="tertiary", use_container_width=True,
                              on_click=lambda cid=chat_id: (
                                  DynamoDatabase.delete(cid, session, curso_impartido_id),
                                  st.session_state.update({
                                      "messages_procesos": [],
                                      "chat_id_procesos": "",
                                      "new_chat_procesos": False
                                  }) if st.session_state.get("chat_id_procesos") == cid else None,
                              ))

                    if st.session_state[f"edit_mode_{chat_id}"]:
                        new_name = st.text_input("Nuevo nombre de chat:", value=item["Name"], key=f"rename_input_{chat_id}")
                        if st.button("✅ Guardar nombre", key=f"save_name_{chat_id}"):
                            DynamoDatabase.editNameManual(chat_id, new_name, session,curso_impartido_id)
                            st.session_state[f"edit_mode_{chat_id}"] = False
                            st.rerun()

                #st.markdown('<hr style="margin-top:4px; margin-bottom:4px;">', unsafe_allow_html=True)
                
                st.markdown("""
        <hr style='border: none; height: 1px; background-color: #d6081f; margin: 8px 0 16px 0;'>
        """, unsafe_allow_html=True)
                
        else:
            st.caption("No tienes conversaciones guardadas.")

    if st.session_state.new_chat_procesos:

        #if not st.session_state.messages_procesos:
        #    st.info(f"Puedes consultar procesos de las siguientes áreas:\n{centros_texto}")
                        
    


        for message in st.session_state.messages_procesos:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        prompt = st.chat_input("Puedes escribir aquí...", key="chat_input_miu")

        

        if prompt:
            st.session_state.messages_procesos.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
                

            invoke_with_retries_procesos(
                lambda q, h: run_cimps_chain(q, h,  st.session_state.curso_impartido_id),
                prompt,
                st.session_state.messages_procesos
            )

       

    else:

        st.success("Haz clic en '✚ Nuevo chat' para iniciar una nueva conversación , o selecciona un chat existente")


if __name__ == "__main__":
    main()