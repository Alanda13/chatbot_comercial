"""
Tela inicial, antes da primeira pergunta (como no ChatGPT): saudação no
meio da tela e sugestões de pergunta em botões.
"""
import base64
from pathlib import Path

import streamlit as st

from config.constants import SUGESTOES
from config.settings import CAMINHO_ICONE


def mostrar_tela_inicial():
    icone = base64.b64encode(Path(CAMINHO_ICONE).read_bytes()).decode()

    st.markdown(
        f"""
        <div class="saudacao">
            <img src="data:image/png;base64,{icone}" alt="">
            <div class="titulo">Olá! Como posso ajudar?</div>
            <div class="subtitulo">
                Pergunte sobre faturamento, metas, desconto ou NPS —
                por filial, RCA, cliente, produto ou período.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container(key="sugestoes"):
        colunas = st.columns(2)

        for indice, sugestao in enumerate(SUGESTOES):
            if colunas[indice % 2].button(
                sugestao["rotulo"], key=f"sugestao_{indice}", use_container_width=True
            ):
                # Na próxima execução a pergunta já vem do ler_pergunta e a
                # tela inicial não aparece mais.
                st.session_state.pergunta_sugerida = sugestao["pergunta"]
                st.rerun()
