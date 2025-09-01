import streamlit as st
import config.dynamo_crud as DynamoDatabase
import uuid
from config.model_ia_cimps import run_procesos_chain 
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



# Cargar variables de entorno
load_dotenv()
client = Client()

import os
# Healthcheck endpoint simulado
if st.query_params.get("check") == "1":
    st.markdown("OK")
    st.stop()



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

    query_params = st.query_params  
    user_id =  query_params.get("user_id", "") 
    persona_id =  query_params.get("id_persona", "")
    servidor = query_params.get("url_request","")   
    curso_impartido_id = query_params.get("curso_impartido_id","")   

    if user_id:
        st.session_state.username =session = user_id  # Guardarlo en la sesión 
        st.session_state.persona_id = persona_id  # Guardarlo en la sesión
        st.session_state.servidor = servidor
        st.session_state.curso_impartido_id = curso_impartido_id 
        print(curso_impartido_id)

    else:
        st.error("⚠️ Acceso denegado.")
        st.stop()


    titulo = f"Asistente del curso impartido - {curso_impartido_id} 🔗"

    mensaje_nuevo_chat = "Nuevo chat"

    st.subheader(titulo, divider='rainbow')

    ## TODO: Obtener información del curso impartido
    ## TODO: Obtener información del usuario que consulta
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

        if st.button(mensaje_nuevo_chat, icon=":material/add:", use_container_width=True):
            st.session_state.chat_id_procesos = str(uuid.uuid4())
            DynamoDatabase.save(st.session_state.chat_id_procesos, session,curso_impartido_id ,  "nuevo chat", [])
            st.session_state.new_chat_procesos = True
            cleanMessages()

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

                st.markdown('<hr style="margin-top:4px; margin-bottom:4px;">', unsafe_allow_html=True)
        else:
            st.caption("No tienes conversaciones guardadas.")

    if st.session_state.new_chat_procesos:

        #if not st.session_state.messages_procesos:
        #    st.info(f"Puedes consultar procesos de las siguientes áreas:\n{centros_texto}")
                        
    


        for message in st.session_state.messages_procesos:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        prompt = st.chat_input("Puedes escribir aquí...")

        

        if prompt:
            st.session_state.messages_procesos.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
                

            invoke_with_retries_procesos(
                lambda q, h: run_procesos_chain(q, h,  st.session_state.curso_impartido_id),
                prompt,
                st.session_state.messages_procesos
            )

       

    else:

        st.success("Haz clic en '✚ Nuevo chat' para iniciar una nueva conversación , o selecciona un chat existente")
        st.divider()





if __name__ == "__main__":
    main()