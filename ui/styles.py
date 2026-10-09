"""
Todo o CSS do app: o visual de chat (balões, campo de digitar, tela
inicial), a tabela e a animação de "digitando".
"""
import json

import streamlit as st

from config.constants import AZUL_FERRONORTE

# Visual de chat das IAs (ChatGPT, Claude, Gemini) com as cores da
# Ferronorte: pergunta em balão à direita, resposta como texto solto,
# campo de digitar arredondado.
_CSS_CHAT = f"""
/* Resposta: sem caixa, só o ícone pequeno ao lado. */
[data-testid="stChatMessage"] {{
    background: transparent;
    padding: 4px 0;
    margin-bottom: 8px;
}}
[data-testid="stChatMessage"] img[alt="assistant avatar"] {{
    width: 28px;
    height: 28px;
}}

/* Pergunta (a resposta é a que tem o avatar em imagem): balão à
   direita, sem avatar. */
[data-testid="stChatMessage"]:not(:has(img[alt="assistant avatar"])) {{
    justify-content: flex-end;
}}
[data-testid="stChatMessage"]:not(:has(img[alt="assistant avatar"])) > div:first-child {{
    display: none;
}}
[data-testid="stChatMessage"]:not(:has(img[alt="assistant avatar"])) [data-testid="stChatMessageContent"] {{
    flex: 0 1 auto;
    /* o Streamlit centraliza (margem automática dos dois lados): encosta
       à direita, como no ChatGPT */
    margin-left: auto !important;
    margin-right: 0 !important;
    max-width: 80%;
    background-color: rgba(14, 94, 166, 0.09);
    border-radius: 18px;
    padding: 10px 16px 2px 16px;
}}
/* Botão de copiar dentro do balão: sem tamanho, o iframe fica com 300px e
   o balão de um "oi" ficava largo. */
[data-testid="stChatMessage"]:not(:has(img[alt="assistant avatar"])) iframe {{
    width: 24px !important;
}}

/* Campo de digitar: pílula com sombra, contorno azulado (azul ao clicar)
   e botão de enviar redondo, azul. Antes contorno, texto de exemplo e
   botão vazio ficavam claros demais ("muito apagado"). */
[data-testid="stChatInput"] > div {{
    border-radius: 26px !important;
    border: 1px solid rgba(14, 94, 166, 0.35) !important;
    box-shadow: 0 2px 12px rgba(30, 41, 56, 0.10);
    background-color: #FFFFFF;
    padding-left: 8px;
}}
[data-testid="stChatInput"] > div:focus-within {{
    border-color: {AZUL_FERRONORTE} !important;
}}
[data-testid="stChatInput"] textarea::placeholder {{
    color: #5B6670 !important;
    opacity: 1;
}}
[data-testid="stChatInputSubmitButton"] {{
    border-radius: 50% !important;
    background-color: {AZUL_FERRONORTE} !important;
    color: #FFFFFF !important;
}}
/* Vazio (nada pra enviar): o mesmo azul, só um pouco mais claro. */
[data-testid="stChatInputSubmitButton"]:disabled {{
    background-color: {AZUL_FERRONORTE} !important;
    opacity: 0.7;
}}

/* Tela inicial: saudação no meio da tela e sugestões em botões. */
.saudacao {{
    text-align: center;
    margin-top: 16vh;
    margin-bottom: 28px;
}}
.saudacao img {{
    width: 56px;
    margin-bottom: 10px;
}}
.saudacao .titulo {{
    font-size: 2rem;
    font-weight: 600;
    color: #1E2938;
}}
.saudacao .subtitulo {{
    font-size: 1rem;
    color: #5b6670;
    margin-top: 4px;
}}
.st-key-sugestoes button {{
    border-radius: 14px;
    background-color: #FFFFFF;
    border: 1px solid rgba(30, 41, 56, 0.14);
    text-align: left;
    padding: 0.7rem 1rem;
    min-height: 3.2rem;
}}
.st-key-sugestoes button:hover {{
    border-color: {AZUL_FERRONORTE};
    color: {AZUL_FERRONORTE};
    background-color: rgba(14, 94, 166, 0.05);
}}

/* Logo maior (na barra lateral e no topo, com a barra recolhida): o
   Streamlit limita a ~2rem e o "Ferronorte" ficava pequeno. */
[data-testid="stSidebarLogo"],
[data-testid="stHeaderLogo"] {{
    height: 2.5rem !important;
    max-height: none !important;
    width: auto;
    max-width: 100%;
}}
[data-testid="stSidebarHeader"] {{
    height: auto !important;
    padding-top: 1rem;
    padding-bottom: 0.5rem;
}}
/* Com a barra aberta, a logo fica no meio dela (e não no canto). */
[data-testid="stSidebarHeader"] > div:first-child {{
    flex: 1;
    display: flex;
    justify-content: center;
}}

/* Barra lateral: linha separando do conteúdo. */
section[data-testid="stSidebar"] {{
    border-right: 1px solid rgba(30, 41, 56, 0.10);
}}
"""

# Tabela ("Ver como tabela"): cabeçalho destacado como nas outras telas do
# comercial, 1ª coluna (nomes) em texto escuro — o Streamlit a deixa cinza,
# como índice — e realce da linha ao passar o mouse.
_CSS_TABELA = """
[data-testid="stTable"] {
    width: fit-content;
    max-width: 100%;
    overflow-x: auto;
}
[data-testid="stTable"] table {
    width: auto;
    border-collapse: collapse;
}
[data-testid="stTable"] th,
[data-testid="stTable"] td {
    border: 1px solid #D5DBE3 !important;
    padding: 6px 14px !important;
}
[data-testid="stTable"] thead th {
    background-color: #E9EDF2;
    color: #1E2938;
    border-bottom: 2px solid #C3CBD5 !important;
}
[data-testid="stTable"] thead th p {
    font-weight: 600;
    white-space: nowrap;
}
[data-testid="stTable"] tbody th,
[data-testid="stTable"] tbody th p {
    color: #1E2938;
    font-weight: 400;
}
[data-testid="stTable"] tbody tr:nth-child(even) th,
[data-testid="stTable"] tbody tr:nth-child(even) td {
    background-color: #EEF2F6 !important;
}
[data-testid="stTable"] p {
    font-variant-numeric: tabular-nums;
}
[data-testid="stTable"] tbody tr:hover th,
[data-testid="stTable"] tbody tr:hover td {
    background-color: #DCE8F4 !important;
}
"""

# Três bolinhas enquanto a resposta não chega.
_CSS_DIGITANDO = """
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
"""


def carregar_css():
    st.markdown(
        "<style>" + _CSS_CHAT + _CSS_TABELA + _CSS_DIGITANDO + "</style>",
        unsafe_allow_html=True,
    )


def mostrar_data_atualizacao(texto: str | None):
    """"Dados atualizados em…" logo abaixo do campo de digitar (como o aviso
    pequeno embaixo do campo do ChatGPT) — o campo fica preso no rodapé,
    então o texto entra pelo CSS."""
    if not texto:
        return

    st.markdown(
        "<style>[data-testid=\"stBottomBlockContainer\"]::after {"
        f" content: {json.dumps(texto, ensure_ascii=False)};"
        " display: block; text-align: center; font-size: 0.75rem;"
        " color: #6b7480; padding-top: 6px; }</style>",
        unsafe_allow_html=True,
    )
