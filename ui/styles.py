"""
Todo o CSS do app: faixa azul, cartões, bordas das mensagens, barra
lateral e a animação de "digitando".
"""
import streamlit as st

from config.constants import AZUL_FERRONORTE

_CSS_GERAL = f"""
    .faixa-topo {{
        background-color: {AZUL_FERRONORTE};
        color: #FFFFFF;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 14px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        flex-wrap: wrap;
        box-shadow: 0 1px 3px rgba(30, 41, 56, 0.12);
    }}
    .faixa-topo .titulo {{
        display: flex;
        align-items: center;
        gap: 12px;
        min-width: 0;
    }}
    .faixa-topo img {{
        width: 40px;
        height: 40px;
        flex-shrink: 0;
        background-color: #FFFFFF;
        border-radius: 8px;
        padding: 4px;
    }}
    .faixa-topo .nome {{
        font-size: 1.2rem;
        font-weight: 700;
        line-height: 1.3;
    }}
    .faixa-topo .subtitulo {{
        font-size: 0.82rem;
        opacity: 0.9;
    }}
    .selo-faixa {{
        background-color: rgba(255, 255, 255, 0.18);
        border-radius: 999px;
        padding: 4px 12px;
        font-size: 0.75rem;
        font-weight: 600;
        white-space: nowrap;
    }}
    .cartao {{
        background-color: #FFFFFF;
        border: 1px solid rgba(30, 41, 56, 0.12);
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 8px;
        box-shadow: 0 2px 6px rgba(30, 41, 56, 0.08);
    }}
    /* Mensagens, campo de digitar e barra lateral com borda suave e
       sombra leve — no fundo claro, branco sobre branco some. */
    [data-testid="stChatMessage"] {{
        background-color: #FFFFFF;
        border: 1px solid rgba(30, 41, 56, 0.12);
        border-radius: 8px;
        box-shadow: 0 2px 6px rgba(30, 41, 56, 0.06);
        padding: 12px 16px;
        margin-bottom: 10px;
    }}
    /* Pergunta do usuário (a resposta tem o avatar em imagem). */
    [data-testid="stChatMessage"]:not(:has(img[alt="assistant avatar"])) {{
        background-color: rgba(14, 94, 166, 0.05);
        border-color: rgba(14, 94, 166, 0.18);
    }}
    [data-testid="stChatInput"] > div {{
        border: 1px solid rgba(30, 41, 56, 0.16);
        box-shadow: 0 2px 8px rgba(30, 41, 56, 0.08);
    }}
    section[data-testid="stSidebar"] {{
        border-right: 1px solid rgba(30, 41, 56, 0.10);
    }}
    .cartao .titulo-cartao {{
        font-weight: 700;
        font-size: 0.95rem;
    }}
    .cartao .subtitulo-cartao {{
        font-size: 0.78rem;
        opacity: 0.6;
        margin-bottom: 8px;
    }}
    .badge-indicador {{
        display: inline-block;
        padding: 2px 10px 2px 8px;
        margin: 2px 4px 2px 0;
        border-radius: 999px;
        font-size: 0.8rem;
        background-color: #FFFFFF;
        border: 1px solid rgba(30, 41, 56, 0.12);
        border-left: 3px solid var(--cor-indicador, {AZUL_FERRONORTE});
    }}
    .legenda-filtros {{
        font-size: 0.8rem;
        opacity: 0.6;
        margin-top: 6px;
    }}
"""

# Botões de exemplo da barra lateral (container com key="painel_perguntas").
_CSS_BARRA_LATERAL = """
            .st-key-painel_perguntas button[kind="secondary"] {
                text-align: left;
                border-radius: 10px;
                padding: 0.6rem 0.85rem;
                background-color: #FFFFFF;
                border: 1px solid rgba(30, 41, 56, 0.12);
                transition: background-color 0.15s ease;
                font-size: 0.88rem;
            }
            .st-key-painel_perguntas button[kind="secondary"]:hover {
                background-color: rgba(14, 94, 166, 0.08);
                border-color: #0E5EA6;
                color: #0E5EA6;
            }
            .st-key-painel_perguntas [data-testid="stVerticalBlock"] {
                gap: 0.2rem;
            }
            .st-key-painel_perguntas p {
                margin: 0 !important;
            }
            .st-key-painel_perguntas .element-container,
            .st-key-painel_perguntas [data-testid="stElementContainer"] {
                margin: 0 !important;
            }
            .rotulo-indicador {
                font-size: 0.8rem;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.03em;
                opacity: 0.65;
                margin-top: 0.5rem;
            }
            .separador-indicador {
                margin: 0.2rem 0 !important;
                border: none;
                border-top: 1px solid rgba(30, 41, 56, 0.10);
            }
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
        "<style>" + _CSS_GERAL + _CSS_BARRA_LATERAL + _CSS_TABELA + _CSS_DIGITANDO
        + "</style>",
        unsafe_allow_html=True,
    )
