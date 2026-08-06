import streamlit as st

from src.chatbot import processar_pergunta

st.set_page_config(
    page_title="Chatbot Comercial Ferronorte",
    page_icon="🤖",
    layout="centered",
)
st.title("🤖 Chatbot Comercial Ferronorte")

st.caption(
    "Consulte Indicadores de NPS em Linguagem Natural."
)

if "mensagens" not in st.session_state:
    st.session_state.mensagens = []

for mensagem in st.session_state.mensagens:
    with st.chat_message(mensagem["papel"]):
        st.markdown(mensagem["conteudo"])

pergunta = st.chat_input(
    "Digite sua pergunta sobre NPS..."
)

if pergunta:
    st.session_state.mensagens.append(
        {
            "papel": "user",
            "conteudo": pergunta,
        }
    )

    with st.chat_message("user"):
        st.markdown(pergunta)

    historico = [
        mensagem
        for mensagem in st.session_state.mensagens[:-1]
    ]

    try:
        with st.chat_message("assistant"):
            with st.spinner("Consultando..."):
                resposta = processar_pergunta(
                    pergunta=pergunta,
                    historico=historico,
                )

            st.markdown(resposta)

        st.session_state.mensagens.append(
            {
                "papel": "assistant",
                "conteudo": resposta,
            }
        )

    except Exception as error:
        mensagem_erro = str(error)

        with st.chat_message("assistant"):
            st.error(mensagem_erro)

        st.session_state.mensagens.append(
            {
                "papel": "assistant",
                "conteudo": mensagem_erro,
            }
        )

        print("\n===== ERRO COMPLETO =====")
        print(error)