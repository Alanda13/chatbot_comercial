"""
Topo da página: faixa azul (com "Dados atualizados em…") e o cartão
"Consultas disponíveis" — mesmo visual das outras telas do comercial
(ex: Separação de Produtos).
"""
import base64
from pathlib import Path

import streamlit as st

from config.constants import AZUL_FERRONORTE, LARANJA_FERRONORTE, VERDE_FERRONORTE
from config.settings import CAMINHO_ICONE
from core.services import atualizador_service as atualizador


def mostrar_cabecalho():
    _icone_base64 = base64.b64encode(Path(CAMINHO_ICONE).read_bytes()).decode()
    _atualizado_em = atualizador.descrever_ultima_atualizacao()
    _selo_atualizacao = (
        f'<span class="selo-faixa">{_atualizado_em}</span>' if _atualizado_em else ""
    )

    st.markdown(
        f"""
        <div class="faixa-topo">
            <div class="titulo">
                <img src="data:image/png;base64,{_icone_base64}" alt="">
                <div>
                    <div class="nome">Chatbot Comercial</div>
                    <div class="subtitulo">
                        Olá! Sou seu assistente virtual. Como posso te ajudar?
                    </div>
                </div>
            </div>
            {_selo_atualizacao}
        </div>
        <div class="cartao">
            <div class="titulo-cartao">Consultas disponíveis</div>
            <div class="subtitulo-cartao">Pergunte em português, do jeito que você falaria.</div>
            <span class="badge-indicador" style="--cor-indicador: {AZUL_FERRONORTE};">💰 Faturamento (R$ e toneladas — anual, mensal e diário)</span>
            <span class="badge-indicador" style="--cor-indicador: {LARANJA_FERRONORTE};">🎯 Metas (faturamento)</span>
            <span class="badge-indicador" style="--cor-indicador: {LARANJA_FERRONORTE};">🎯 Metas (tonelada) — 2024 a 2026</span>
            <span class="badge-indicador" style="--cor-indicador: {AZUL_FERRONORTE};">🏷️ Desconto</span>
            <span class="badge-indicador" style="--cor-indicador: {VERDE_FERRONORTE};">⭐ NPS</span>
            <div class="legenda-filtros">
                Tudo por <b>filial, RCA, supervisor, cliente, produto ou período</b>,
                além da lista de filiais.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
