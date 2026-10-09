"""
A tabela embaixo da resposta ("📊 Ver como tabela") e o botão de
baixar em Excel.
"""
import re
from datetime import datetime

import streamlit as st

from config.settings import CAMINHO_LOGO_SIDEBAR
from ui.exportar_excel import gerar_excel
from ui.formatacao import descrever_periodo, preparar_tabela


# "R$ 3.831.746,29", "−R$ 963,53", "2,29%", "+5,64%", "1.234", "sem dados".
_VALOR = re.compile(r"^([+−-]?(R\$ )?[\d.,]+%?|sem dados|menos de 0,01%)$")


def _colunas_de_valor(tabela):
    """Colunas em que todas as células são número, R$ ou %."""
    return [
        coluna for coluna in tabela.columns
        if tabela[coluna].astype(str).str.match(_VALOR).all()
    ]


def exibir_tabela(dados_tabela, texto_referencia, chave, nome_ferramenta=None, pergunta=None):
    """Renderiza a tabela formatada + botão de download em Excel (com a
    pergunta como título da planilha)."""
    legenda = descrever_periodo(dados_tabela, texto_referencia)
    if legenda:
        st.caption(legenda)

    tabela = preparar_tabela(dados_tabela, texto_referencia, nome_ferramenta)

    # Converte tudo pra texto antes de exibir — evita erro do pyarrow
    # quando uma coluna mistura números com texto (ex: NPS com valor
    # numérico em alguns meses e "sem dados" em outros). O Excel
    # (mais abaixo) continua usando os dados originais, sem essa
    # conversão.
    tabela_exibicao = tabela.astype(str)

    # st.table é uma tabela estática, sem barra de ferramentas — não
    # tem botão de tela cheia nem de baixar CSV, evitando os problemas
    # de layout que apareciam com st.dataframe.
    tabela_exibicao = tabela_exibicao.set_index(tabela_exibicao.columns[0])
    colunas_de_valor = _colunas_de_valor(tabela_exibicao)

    # Espaço que não quebra: o valor nunca vira "R$" numa linha e o número
    # na de baixo (só na tela — o Excel usa a tabela original).
    for coluna in colunas_de_valor:
        tabela_exibicao[coluna] = tabela_exibicao[coluna].str.replace(" ", "\u00a0")

    # Valores (R$, %, números) à direita, pra ficarem um embaixo do
    # outro; texto (nomes de produto, família…) continua à esquerda. Uma
    # regra por COLUNA (título e células): o estilo célula a célula
    # (set_properties) quebra quando a 1ª coluna repete valores (ex: "os 5
    # RCAs de cada mês" — "Janeiro" 5 vezes).
    st.table(
        tabela_exibicao.style.set_table_styles({
            coluna: [{"selector": "", "props": "text-align: right !important;"}]
            for coluna in colunas_de_valor
        })
        if colunas_de_valor else tabela_exibicao
    )

    agora = datetime.now()
    subtitulo = " · ".join(
        parte for parte in (legenda, f"Gerado em {agora:%d/%m/%Y às %H:%M}") if parte
    )

    st.download_button(
        label="⬇️ Baixar em Excel",
        data=gerar_excel(
            tabela,
            titulo=pergunta or "Chatbot Comercial Ferronorte",
            subtitulo=subtitulo,
            caminho_logo=CAMINHO_LOGO_SIDEBAR,
        ),
        file_name=f"Chatbot_Ferronorte_{agora:%d.%m.%Y}.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument"
            ".spreadsheetml.sheet"
        ),
        key=f"download_{chave}",
    )
