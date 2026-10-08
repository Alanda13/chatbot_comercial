"""
Estado inicial da sessão: o histórico do chat e a pergunta de exemplo
clicada na barra lateral.
"""
import streamlit as st


def init_state():
    if "mensagens" not in st.session_state:
        st.session_state.mensagens = []

    if "pergunta_sugerida" not in st.session_state:
        st.session_state.pergunta_sugerida = None
