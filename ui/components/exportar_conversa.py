"""
"Esta conversa" na barra lateral: baixar ou copiar a conversa inteira
(perguntas, respostas e tabelas) — o histórico some quando a página é
fechada, então quem quiser guardar baixa ou cola em outro lugar.
"""
import json
import re
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components

from ui.formatacao import preparar_tabela, vale_a_pena_mostrar_tabela


def _sem_markdown(texto: str) -> str:
    """Tira o negrito do markdown (**texto**) — no arquivo ficava cru."""
    return re.sub(r"\*\*(.+?)\*\*", r"\1", texto)


def montar_texto_da_conversa(mensagens: list[dict], quando: datetime) -> str:
    """A conversa em texto simples: cada pergunta, a resposta e a tabela."""
    partes = [f"Chatbot Comercial Ferronorte — conversa de {quando:%d/%m/%Y às %H:%M}"]

    for mensagem in mensagens:
        conteudo = _sem_markdown(mensagem.get("conteudo") or "")

        if mensagem["papel"] == "user":
            partes.append(f"Você: {conteudo}")
            continue

        partes.append(f"Chatbot: {conteudo}")
        dados = mensagem.get("dados_tabela")
        ferramenta = mensagem.get("nome_ferramenta")

        if dados and vale_a_pena_mostrar_tabela(dados, conteudo, ferramenta):
            tabela = preparar_tabela(dados, conteudo, ferramenta)
            partes.append(tabela.to_string(index=False))

    return "\n\n".join(partes) + "\n"


def _botao_copiar_conversa(texto: str) -> None:
    """Botão "Copiar conversa" — num iframe (components.html), o único
    lugar do Streamlit com permissão de copiar (ver chat.botao_copiar)."""
    texto_js = json.dumps(texto).replace("</", "<\\/")
    components.html(
        f"""
        <style>
            html, body {{ margin: 0; padding: 0; background: transparent; }}
            button {{
                width: 100%; height: 38px; cursor: pointer;
                font-family: "Source Sans Pro", sans-serif; font-size: 14px;
                color: #1E2938; background: #FFFFFF;
                border: 1px solid rgba(30, 41, 56, 0.2); border-radius: 8px;
            }}
            button:hover {{ border-color: #0E5EA6; color: #0E5EA6; }}
        </style>
        <button id="copiar">📋 Copiar conversa</button>
        <script>
        const botao = document.getElementById("copiar");
        botao.addEventListener("click", () => {{
            navigator.clipboard.writeText({texto_js});
            botao.textContent = "✅ Copiado!";
            setTimeout(() => {{ botao.textContent = "📋 Copiar conversa"; }}, 1500);
        }});
        </script>
        """,
        height=40,
    )


def mostrar_exportacao():
    """Chamada no FIM do app.py, depois da resposta — assim a conversa
    baixada já inclui a última pergunta."""
    mensagens = st.session_state.get("mensagens") or []

    if not mensagens:
        return

    agora = datetime.now()
    texto = montar_texto_da_conversa(mensagens, agora)

    with st.sidebar:
        with st.container(border=True):
            st.markdown("#### 💬 Esta conversa")
            st.caption("Guarde antes de fechar: o histórico some com a página.")
            st.download_button(
                "⬇️ Baixar conversa",
                data=texto.encode("utf-8"),
                file_name=f"conversa_chatbot_{agora:%Y-%m-%d_%Hh%M}.txt",
                mime="text/plain",
                use_container_width=True,
                key="baixar_conversa",
            )
            _botao_copiar_conversa(texto)
