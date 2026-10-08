import streamlit as st

from config.settings import CAMINHO_ICONE, CAMINHO_LOGO_SIDEBAR, TITULO_PAGINA
from core.services import atualizador_service as atualizador
from ui.components.barra_lateral import mostrar_barra_lateral
from ui.components.tela_inicial import mostrar_tela_inicial
from ui.components.chat import ler_pergunta, mostrar_historico, responder
from ui.components.exportar_conversa import mostrar_exportacao
from ui.state import init_state
from ui.styles import carregar_css, mostrar_data_atualizacao


st.set_page_config(
    page_title=TITULO_PAGINA,
    page_icon=CAMINHO_ICONE,
    layout="centered",
)

st.logo(CAMINHO_LOGO_SIDEBAR, size="large")

# css

carregar_css()

mostrar_data_atualizacao(atualizador.descrever_ultima_atualizacao())

# pra atualizar os csvs do oracle em 2 plano
if st.runtime.exists():  # não roda quando o app é só importado (testes)
    atualizador.iniciar()

# estado inicial

init_state()

# barra lateral e chat

mostrar_barra_lateral()

# A pergunta é lida antes de desenhar: com ela, a tela inicial já não aparece.
pergunta = ler_pergunta()

if not st.session_state.mensagens and not pergunta:
    mostrar_tela_inicial()

mostrar_historico()

if pergunta:
    responder(pergunta)

# baixar / copiar a conversa (no fim: já inclui a última resposta)

mostrar_exportacao()
