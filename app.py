import streamlit as st

from config.settings import CAMINHO_ICONE, CAMINHO_LOGO_SIDEBAR, TITULO_PAGINA
from core.services import atualizador_service as atualizador
from ui.components.barra_lateral import mostrar_barra_lateral
from ui.components.cabecalho import mostrar_cabecalho
from ui.components.chat import ler_pergunta, mostrar_historico, responder
from ui.state import init_state
from ui.styles import carregar_css


st.set_page_config(
    page_title=TITULO_PAGINA,
    page_icon=CAMINHO_ICONE,
    layout="centered",
)

st.logo(CAMINHO_LOGO_SIDEBAR, size="large")

# css

carregar_css()

# topo: faixa azul + "Consultas disponíveis"

mostrar_cabecalho()

# pra atualizar os csvs do oracle em 2 plano
if st.runtime.exists():  # não roda quando o app é só importado (testes)
    atualizador.iniciar()

# estado inicial

init_state()

# barra lateral e chat

mostrar_barra_lateral()
mostrar_historico()

pergunta = ler_pergunta()

if pergunta:
    responder(pergunta)
