import streamlit as st

from src.chatbot import processar_pergunta
from src.exceptions import ChatbotError
from src.logger import obter_logger

logger = obter_logger(__name__)

st.set_page_config(
    page_title="Chatbot Comercial Ferronorte",
    page_icon="🤖",
    layout="centered",
)
st.title("🤖 Chatbot Comercial Ferronorte")

st.caption(
    "Consulte Informações sobre Indicadores Comerciais."
)

if "mensagens" not in st.session_state:
    st.session_state.mensagens = []

for mensagem in st.session_state.mensagens:
    with st.chat_message(mensagem["papel"]):
        st.text(mensagem["conteudo"])

pergunta = st.chat_input(
    "Digite sua pergunta sobre algum indicador comercial..."
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

            st.text(resposta)

        st.session_state.mensagens.append(
            {
                "papel": "assistant",
                "conteudo": resposta,
            }
        )

    except ChatbotError as error:
        mensagem_erro = str(error)

        with st.chat_message("assistant"):
            st.error(mensagem_erro)

        st.session_state.mensagens.append(
            {
                "papel": "assistant",
                "conteudo": mensagem_erro,
            }
        )

        logger.warning("Erro ao processar pergunta: %s", error)

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

        logger.exception("Erro inesperado ao processar pergunta")