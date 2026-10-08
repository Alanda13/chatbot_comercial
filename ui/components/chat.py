"""
O chat: histórico de mensagens, campo de digitar, botão de copiar e o
envio da pergunta (com a bolinha de "digitando" até a resposta chegar).
"""
import json

import streamlit as st
import streamlit.components.v1 as components

from config.settings import CAMINHO_ICONE
from core.services.chatbot_service import processar_pergunta
from core.exceptions import ChatbotError
from core.logger import obter_logger
from core.repositories.perguntas_repository import registrar_pergunta
from ui.components.tabela import exibir_tabela
from ui.formatacao import escapar_para_markdown, vale_a_pena_mostrar_tabela

logger = obter_logger(__name__)

AVATAR_POR_PAPEL = {"user": "🧑‍💼", "assistant": CAMINHO_ICONE}


def botao_copiar(texto):
    """
    Botão de copiar o texto de uma mensagem.

    Roda dentro de components.html (iframe isolado) de propósito: um
    botão colado direto via st.markdown fica embaixo do "toolbar" que
    o próprio Streamlit desenha por cima de blocos de texto ao passar
    o mouse (o mesmo mecanismo do botão de copiar do st.code) — o
    clique é capturado por esse toolbar antes de chegar no botão, e
    nada é copiado. O iframe do components.html não tem esse problema
    e é a única parte do Streamlit com permissão de "clipboard-write"
    liberada de verdade.
    """
    texto_js = json.dumps(texto).replace("</", "<\\/")
    components.html(
        f"""
        <style>
            html, body {{
                margin: 0;
                padding: 0;
                background: transparent;
                overflow: hidden;
                display: flex;
                align-items: center;
                gap: 8px;
            }}
        </style>
        <button id="botao-copiar" title="Copiar mensagem" style="
            all: unset; cursor: pointer; display: inline-flex;
            align-items: center; justify-content: center;
            width: 22px; height: 22px; border-radius: 5px;
            color: #9aa5b1;
        ">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="2" stroke-linecap="round"
                 stroke-linejoin="round">
                <rect x="9" y="9" width="13" height="13" rx="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
        </button>
        <script>
        document.getElementById("botao-copiar").addEventListener("click", function () {{
            navigator.clipboard.writeText({texto_js});
            this.style.color = "#3ba55d";
            setTimeout(() => {{ this.style.color = "#9aa5b1"; }}, 900);
        }});
        </script>
        """,
        height=22,
    )


def mostrar_historico():
    for indice_mensagem, mensagem in enumerate(st.session_state.mensagens):
        with st.chat_message(
            mensagem["papel"], avatar=AVATAR_POR_PAPEL.get(mensagem["papel"])
        ):
            st.markdown(escapar_para_markdown(mensagem["conteudo"]))
            botao_copiar(mensagem["conteudo"])

            if mensagem.get("dados_tabela") and vale_a_pena_mostrar_tabela(
                mensagem["dados_tabela"],
                mensagem.get("conteudo", ""),
                mensagem.get("nome_ferramenta"),
            ):
                with st.expander("📊 Ver como tabela"):
                    exibir_tabela(
                        mensagem["dados_tabela"],
                        mensagem.get("conteudo", ""),
                        chave=f"historico_{indice_mensagem}",
                        nome_ferramenta=mensagem.get("nome_ferramenta"),
                    )


def ler_pergunta():
    """A pergunta digitada ou, se não houver, a de exemplo clicada."""
    pergunta = st.chat_input(
        "Digite sua pergunta sobre algum indicador comercial..."
    )

    if not pergunta and st.session_state.pergunta_sugerida:
        pergunta = st.session_state.pergunta_sugerida
        st.session_state.pergunta_sugerida = None

    return pergunta


def responder(pergunta):
    registrar_pergunta(pergunta)

    st.session_state.mensagens.append(
        {
            "papel": "user",
            "conteudo": pergunta,
        }
    )

    with st.chat_message("user", avatar=AVATAR_POR_PAPEL["user"]):
        st.markdown(escapar_para_markdown(pergunta))
        botao_copiar(pergunta)

    historico = [
        mensagem
        for mensagem in st.session_state.mensagens[:-1]
    ]

    with st.chat_message("assistant", avatar=AVATAR_POR_PAPEL["assistant"]):
        placeholder = st.empty()
        placeholder.markdown(
            """
            <div class="digitando">
                <span></span><span></span><span></span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # A bolha de "digitando" é sempre substituída pelo conteúdo
        # final, seja a resposta ou o erro — nunca fica travada na tela.
        try:
            resposta, dados_tabela, nome_ferramenta = processar_pergunta(
                pergunta=pergunta,
                historico=historico,
            )
            # Com formatação (negrito, listas, tabelas) — as análises vêm em
            # markdown; com st.text os **asteriscos** apareciam crus.
            placeholder.markdown(escapar_para_markdown(resposta))

            botao_copiar(resposta)

            if dados_tabela and vale_a_pena_mostrar_tabela(
                dados_tabela, resposta, nome_ferramenta
            ):
                with st.expander("📊 Ver como tabela"):
                    exibir_tabela(
                        dados_tabela,
                        resposta,
                        chave="atual",
                        nome_ferramenta=nome_ferramenta,
                    )

            st.session_state.mensagens.append(
                {
                    "papel": "assistant",
                    "conteudo": resposta,
                    "dados_tabela": dados_tabela,
                    "nome_ferramenta": nome_ferramenta,
                }
            )

        except ChatbotError as error:
            mensagem_erro = str(error)
            placeholder.error(mensagem_erro)

            st.session_state.mensagens.append(
                {
                    "papel": "assistant",
                    "conteudo": mensagem_erro,
                }
            )

            logger.warning("Erro ao processar pergunta: %s", error)

        except Exception as error:
            mensagem_erro = str(error)
            placeholder.error(mensagem_erro)

            st.session_state.mensagens.append(
                {
                    "papel": "assistant",
                    "conteudo": mensagem_erro,
                }
            )

            logger.exception("Erro inesperado ao processar pergunta")
