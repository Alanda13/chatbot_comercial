"""
Barra lateral: "Nova conversa" (como no ChatGPT). O "Esta conversa"
(baixar/copiar) entra no fim do app.py — ver exportar_conversa.py.
"""
import streamlit as st


def mostrar_barra_lateral():
    with st.sidebar:
        if st.button("＋  Nova conversa", use_container_width=True, type="primary"):
            st.session_state.mensagens = []
            st.session_state.pergunta_sugerida = None
            st.rerun()
