import streamlit as st

from src.chatbot import processar_pergunta
from src.exceptions import ChatbotError
from src.logger import obter_logger
from src.perguntas_log import (
    contar_perguntas_registradas,
    obter_perguntas_frequentes,
    registrar_pergunta,
)

logger = obter_logger(__name__)

PERGUNTAS_EXEMPLO = [
    "Qual o faturamento de Timon em julho de 2025?",
    "Qual o NPS geral da empresa?",
    "Quanto faturamos hoje?",
    "Compare o faturamento de Timon em 2024 e 2025.",
]

QUANTIDADE_MINIMA_PARA_FREQUENTES = 5
LIMITE_CARACTERES_ROTULO = 42


def _formatar_rotulo(pergunta: str, limite: int = LIMITE_CARACTERES_ROTULO) -> str:
    """
    Formata a pergunta para exibição no botão: primeira letra
    maiúscula e truncada em uma linha, sem alterar o texto original
    que é de fato enviado ao chat.
    """
    texto = pergunta.strip()

    if texto and not texto[0].isupper():
        texto = texto[0].upper() + texto[1:]

    if len(texto) > limite:
        texto = texto[:limite].rstrip() + "…"

    return texto

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

if "pergunta_sugerida" not in st.session_state:
    st.session_state.pergunta_sugerida = None

with st.sidebar:
    total_perguntas = contar_perguntas_registradas()

    with st.container(border=True):
        if total_perguntas >= QUANTIDADE_MINIMA_PARA_FREQUENTES:
            st.markdown("#### 🔥 Perguntas mais frequentes")
            sugestoes = [
                item["pergunta"]
                for item in obter_perguntas_frequentes(limite=5)
            ]
        else:
            st.markdown("#### 💡 Experimente perguntar")
            sugestoes = PERGUNTAS_EXEMPLO

        st.caption("Clique numa pergunta para enviá-la ao chat.")

        for indice, sugestao in enumerate(sugestoes):
            if st.button(
                _formatar_rotulo(sugestao),
                key=f"sugestao_{indice}",
                use_container_width=True,
                help=sugestao,
            ):
                st.session_state.pergunta_sugerida = sugestao

for mensagem in st.session_state.mensagens:
    with st.chat_message(mensagem["papel"]):
        st.text(mensagem["conteudo"])

pergunta = st.chat_input(
    "Digite sua pergunta sobre algum indicador comercial..."
)

if not pergunta and st.session_state.pergunta_sugerida:
    pergunta = st.session_state.pergunta_sugerida
    st.session_state.pergunta_sugerida = None

if pergunta:
    registrar_pergunta(pergunta)

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
            placeholder = st.empty()
            placeholder.markdown(
                """
                <div class="digitando">
                    <span></span><span></span><span></span>
                </div>
                <style>
                .digitando { display: flex; gap: 4px; padding: 6px 0; }
                .digitando span {
                    width: 8px; height: 8px; border-radius: 50%;
                    background-color: currentColor; opacity: 0.4;
                    animation: piscar 1.4s infinite ease-in-out both;
                }
                .digitando span:nth-child(1) { animation-delay: -0.32s; }
                .digitando span:nth-child(2) { animation-delay: -0.16s; }
                @keyframes piscar {
                    0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
                    40% { transform: scale(1); opacity: 1; }
                }
                </style>
                """,
                unsafe_allow_html=True,
            )

            resposta = processar_pergunta(
                pergunta=pergunta,
                historico=historico,
            )

            placeholder.text(resposta)

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