# ✅ 1. Build del grafo (separado para reuso)
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import add_messages
from typing import TypedDict, Annotated

# 🟢 Estado global
class State(TypedDict):
    messages: Annotated[list, add_messages]

def build_cimps_graph(curso_impartido):
    graph_builder = StateGraph(State)

    # 🔹 Tools de ejemplo
    tools = [tool_obtener_notas, tool_ver_anuncio_curso]

    # 🔹 LLM con tools habilitadas
    llm_with_tools = model.bind_tools(tools)

    # 🔹 Nodo principal (chatbot)
    def chatbot_node(state: State):
        return {"messages": [llm_with_tools.invoke(state["messages"])]}

    graph_builder.add_node("chatbot", chatbot_node)
    graph_builder.add_node("tools", ToolNode(tools=tools))

    # 🔹 Condicional: si el LLM pidió tool_call, ve al nodo de tools
    graph_builder.add_conditional_edges("chatbot", tools_condition, "tools")
    graph_builder.add_edge("tools", "chatbot")
    graph_builder.add_edge(START, "chatbot")

    return graph_builder.compile()

# ✅ 2. Streaming adaptado para Streamlit
def invoke_with_retries_procesos(run_graph_fn, question, history, max_retries=10):
    attempt = 0
    warning_placeholder = st.empty()

    with st.chat_message("assistant"):
        response_placeholder = st.empty()

        while attempt < max_retries:
            try:
                print(f"Reintento {attempt + 1} de {max_retries}")
                full_response = ""

                # Construir grafo e invocar en modo streaming
                graph = run_graph_fn()  # <--- pasas una función que devuelva tu grafo compilado
                state = {"messages": history + [{"role": "user", "content": question}]}

                for event in graph.stream(state):
                    # 🔍 Filtra solo eventos que contengan mensajes nuevos
                    if "messages" in event:
                        last_msg = event["messages"][-1]
                        # Solo mostramos si es respuesta del asistente
                        if last_msg.type == "ai":
                            full_response = last_msg.content
                            response_placeholder.markdown(full_response)

                # ✅ Guardar en session_state y DynamoDB
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

                if DynamoDatabase.getNameChat(
                    st.session_state.chat_id_procesos,
                    st.session_state.username,
                    st.session_state.curso_impartido_id
                ) == "nuevo chat":
                    DynamoDatabase.editName(
                        st.session_state.chat_id_procesos,
                        question,
                        st.session_state.username,
                        st.session_state.curso_impartido_id
                    )
                    st.rerun()

                warning_placeholder.empty()
                return

            except Exception as e:
                attempt += 1
                if attempt == 1:
                    warning_placeholder.markdown(
                        "⌛ Esperando generación de respuesta...",
                        unsafe_allow_html=True
                    )
                print(f"Error inesperado en reintento {attempt}: {str(e)}")
                if attempt == max_retries:
                    warning_placeholder.markdown(
                        "⚠️ **No fue posible generar la respuesta, vuelve a intentar.**",
                        unsafe_allow_html=True
                    )
