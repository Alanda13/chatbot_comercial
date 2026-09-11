import base64
import io
import re
from pathlib import Path

import streamlit as st
import pandas as pd
from src.chatbot import processar_pergunta
from src.exceptions import ChatbotError
from src.logger import obter_logger
from src.perguntas_log import registrar_pergunta

logger = obter_logger(__name__)

# Perguntas norteadoras: uma por indicador, já mostrando a resposta,
# pra dar uma ideia rápida do que o chatbot responde.
#
# "resposta" fixa só é usada para períodos FECHADOS (já aconteceram e
# não mudam mais) de indicadores que vêm de base histórica (CSV) —
# faturamento e meta. Quando "resposta" é None, o clique busca o dado
# ao vivo (mesmo fluxo de uma pergunta digitada), porque o indicador é
# ligado ao banco e muda a cada consulta.
PERGUNTAS_NORTEADORAS = [
    {
        "categoria": "💰 Faturamento",
        "pergunta": "Qual foi o faturamento de Timon em julho de 2025?",
        "resposta": (
            "O faturamento da filial Timon em julho de 2025 foi de "
            "R$ 10.610.613,36."
        ),
    },
    {
        "categoria": "🎯 Meta de faturamento",
        "pergunta": "Qual a meta de Timon em julho de 2025?",
        "resposta": (
            "A meta de faturamento da filial Timon em julho de 2025 "
            "foi de R$ 8.671.193,51."
        ),
    },
    {
        "categoria": "🎯 Meta de tonelada",
        "pergunta": "Qual a meta de tonelada de Timon em 2025?",
        "resposta": (
            "A meta de tonelada da filial Timon em 2025 é de "
            "11.462,34 toneladas."
        ),
    },
    {
        "categoria": "⭐ NPS",
        "pergunta": "Qual o NPS do mês passado?",
        "resposta": "O NPS do mês passado (agosto de 2026) foi de 90,74.",
    },
]


def escapar_para_markdown(texto):
    """
    Evita que o Streamlit interprete "$" como abertura de fórmula
    matemática (LaTeX) — isso quebra a exibição de valores em reais
    (ex: "R$ 10,00 ... R$ 20,00" vira uma fórmula em vez de texto)
    sempre que o texto passa por st.markdown/st.caption. Usa a
    entidade HTML do "$" em vez de escapar com "\\$", porque o
    Streamlit mostra a barra invertida ao invés de escondê-la.
    """
    return texto.replace("$", "&#36;")

MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}

# Palavra que pode aparecer na pergunta -> coluna correspondente nos
# dados. Usado pra mostrar na tabela só o que a pessoa perguntou, em
# vez de todas as colunas que a consulta retornou.
PALAVRAS_PARA_COLUNA = {
    "faturamento": "faturamento",
    "venda bruta": "venda_bruta",
    "desconto": "valor_desconto",
    "tonelada": "toneladas",
    "peso": "peso_liquido",
    "nota": "quantidade_notas",
    "nps": "nps",
}

COLUNAS_MONETARIAS = {"faturamento", "venda_bruta", "valor_desconto"}

RENOMEAR_COLUNAS = {
    "filial": "Filial",
    "rca_nome": "RCA",
    "rca": "Código RCA",
    "codigo": "Código",
    "mes": "Mês",
    "ano": "Ano",
    "faturamento": "Faturamento",
    "venda_bruta": "Venda Bruta",
    "valor_desconto": "Desconto",
    "toneladas": "Toneladas",
    "peso_liquido": "Peso Líquido",
    "quantidade_notas": "Qtd. Notas",
    "nps": "NPS",
    "meta_tonelada_rca": "Meta Tonelada (RCA)",
    "meta_tonelada_filial": "Meta Tonelada (Filial)",
    "diferenca_mes_anterior": "Diferença (mês anterior)",
    "percentual_mes_anterior": "Variação (mês anterior)",
    "diferenca_ano_anterior": "Diferença (ano anterior)",
    "percentual_ano_anterior": "Variação (ano anterior)",
}


def formatar_moeda(valor):
    """Formata um número no padrão R$ 91.783.909,07."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""

    texto = f"{valor:,.2f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def formatar_percentual_com_sinal(valor):
    """Formata um percentual com sinal + explícito (ex: +5.64%)."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return "sem dados"

    sinal = "+" if valor >= 0 else ""
    return f"{sinal}{valor}%"


def ocultar_repeticoes_consecutivas(df, coluna):
    """
    Deixa em branco as repetições consecutivas de uma coluna (ex: o
    nome da filial repetido em toda linha) — só mostra o valor na
    primeira linha de cada grupo, evitando poluição visual.
    """
    if coluna not in df.columns or len(df) <= 1:
        return df

    valores = df[coluna].tolist()
    novos_valores = []
    valor_anterior = object()  # sentinela, nunca é igual a nada real

    for valor in valores:
        if valor == valor_anterior:
            novos_valores.append("")
        else:
            novos_valores.append(valor)
            valor_anterior = valor

    df[coluna] = novos_valores
    return df


def preparar_tabela(dados_tabela, texto_referencia):
    """
    Monta a tabela pronta pra exibição: filtra só as colunas que o
    texto de referência menciona (a resposta do chatbot, de
    preferência — mais confiável que a pergunta digitada, que pode
    ter erro de digitação), troca número do mês pelo nome, formata
    moeda e renomeia os títulos das colunas pra português legível.
    """
    df = pd.DataFrame(dados_tabela)

    # Formato especial: comparação entre exatamente 2 anos, já vem
    # com valor_ano_1/valor_ano_2/diferenca/percentual prontos do
    # queries.py — monta a tabela com os anos como nome de coluna.
    if "valor_ano_1" in df.columns and "valor_ano_2" in df.columns:
        ano_1 = df["ano_1"].iloc[0]
        ano_2 = df["ano_2"].iloc[0]

        df["mes"] = df["mes"].map(MESES_PT).fillna(df["mes"])

        eh_monetario = any(
            palavra in texto_referencia.lower()
            for palavra in ("faturamento", "venda bruta", "desconto")
        )

        def formatar_valor(valor):
            if valor is None or (isinstance(valor, float) and pd.isna(valor)):
                return "sem dados"
            return formatar_moeda(valor) if eh_monetario else valor

        def formatar_percentual(valor):
            if valor is None or (isinstance(valor, float) and pd.isna(valor)):
                return "sem dados"
            sinal = "+" if valor >= 0 else ""
            return f"{sinal}{valor}%"

        tabela_comparacao = pd.DataFrame({
            "Mês": df["mes"],
            str(ano_1): df["valor_ano_1"].apply(formatar_valor),
            str(ano_2): df["valor_ano_2"].apply(formatar_valor),
            "Variação": df["percentual"].apply(formatar_percentual),
        })

        return tabela_comparacao

    # Se não tem coluna "ano" pronta mas tem "data_inicial" (formato
    # YYYY-MM-DD), extrai o ano de lá — usado em consultas por
    # filial+período que não passam pelo agrupamento mês a mês. Isso
    # precisa vir ANTES da checagem de pivô Filial x Ano logo abaixo,
    # senão o pivô nunca detecta os 2 anos nesse formato de dado.
    if "ano" not in df.columns and "data_inicial" in df.columns:
        df["ano"] = df["data_inicial"].str.slice(0, 4)

    # Formato especial: filiais comparadas entre EXATAMENTE 2 anos
    # (sem ser mês a mês) — pivota pra Filial | ano_1 | ano_2 | Variação,
    # no mesmo espírito da comparação mensal acima.
    if (
        "filial" in df.columns
        and "ano" in df.columns
        and "mes" not in df.columns
        and df["ano"].nunique() == 2
    ):
        anos_ordenados = sorted(df["ano"].unique())
        ano_1, ano_2 = anos_ordenados[0], anos_ordenados[1]

        coluna_valor = "nps" if "nps" in df.columns else None
        if coluna_valor is None:
            for candidata in PALAVRAS_PARA_COLUNA.values():
                if candidata in df.columns:
                    coluna_valor = candidata
                    break

        eh_monetario = coluna_valor in COLUNAS_MONETARIAS

        linhas = []
        for nome_filial in df["filial"].unique():
            valor_1 = df[
                (df["filial"] == nome_filial) & (df["ano"] == ano_1)
            ][coluna_valor]
            valor_2 = df[
                (df["filial"] == nome_filial) & (df["ano"] == ano_2)
            ][coluna_valor]

            valor_1 = valor_1.iloc[0] if len(valor_1) else None
            valor_2 = valor_2.iloc[0] if len(valor_2) else None

            if valor_1 is None or valor_2 is None or pd.isna(valor_1) or pd.isna(valor_2) or valor_1 == 0:
                percentual_texto = "sem dados"
            else:
                percentual = round((valor_2 - valor_1) / abs(valor_1) * 100, 2)
                sinal = "+" if percentual >= 0 else ""
                percentual_texto = f"{sinal}{percentual}%"

            def formatar(valor):
                if valor is None or pd.isna(valor):
                    return "sem dados"
                return formatar_moeda(valor) if eh_monetario else valor

            linhas.append({
                "Filial": nome_filial,
                str(ano_1): formatar(valor_1),
                str(ano_2): formatar(valor_2),
                "Variação": percentual_texto,
            })

        return pd.DataFrame(linhas)

    # Se a resposta em texto só menciona ALGUMAS das filiais que vieram
    # na consulta (ex: "qual filial teve o maior NPS" — a IA já filtrou
    # pra responder só a vencedora), a tabela segue o mesmo filtro, em
    # vez de mostrar a lista crua com todas as filiais da consulta.
    #
    # Nomes mais LONGOS são checados primeiro, e o trecho encontrado é
    # "consumido" do texto — sem isso, um nome curto que é prefixo de
    # outro (ex: "FERRONORTE AREINHA" dentro de "FERRONORTE AREINHA
    # LOGISTICA") apareceria como falso positivo.
    if "filial" in df.columns:
        texto_restante = texto_referencia.lower()
        nomes_ordenados = sorted(
            df["filial"].unique(), key=lambda nome: -len(str(nome))
        )
        filiais_na_resposta = []

        for nome_filial in nomes_ordenados:
            nome_lower = str(nome_filial).lower()
            if nome_lower in texto_restante:
                filiais_na_resposta.append(nome_filial)
                texto_restante = texto_restante.replace(nome_lower, "")

        if filiais_na_resposta and len(filiais_na_resposta) < df["filial"].nunique():
            df = df[df["filial"].isin(filiais_na_resposta)]

    if "rca_nome" in df.columns:
        texto_restante = texto_referencia.lower()
        nomes_ordenados = sorted(
            df["rca_nome"].dropna().unique(), key=lambda nome: -len(str(nome))
        )
        rcas_na_resposta = []

        for nome_rca in nomes_ordenados:
            nome_lower = str(nome_rca).lower()
            if nome_lower in texto_restante:
                rcas_na_resposta.append(nome_rca)
                texto_restante = texto_restante.replace(nome_lower, "")

        if rcas_na_resposta and len(rcas_na_resposta) < df["rca_nome"].nunique():
            df = df[df["rca_nome"].isin(rcas_na_resposta)]

    colunas_base = [
        coluna
        for coluna in ("filial", "rca_nome", "rca", "codigo", "ano", "mes")
        if coluna in df.columns
    ]

    # Se já tem o nome do RCA (rca_nome), não precisa mostrar também o
    # código cru (rca) — uma coluna só de identificação é mais limpo.
    if "rca_nome" in colunas_base and "rca" in colunas_base:
        colunas_base.remove("rca")

    # Se só tem UM ano nos dados, tira a coluna "ano" da tabela — ela
    # já aparece na legenda acima ("Ano: 2025"), repetir em toda
    # linha é redundante. Só mantém quando há vários anos misturados.
    if "ano" in colunas_base and df["ano"].nunique() <= 1:
        colunas_base.remove("ano")

    texto_lower = texto_referencia.lower()
    colunas_metricas = [
        coluna
        for palavra, coluna in PALAVRAS_PARA_COLUNA.items()
        if palavra in texto_lower and coluna in df.columns
    ]

    # "Faturamento" às vezes aparece no texto só como nome genérico do
    # indicador (ex: "faturamento em toneladas"), não significando que
    # o valor em R$ também foi pedido. Só mantém a coluna de R$ junto
    # com toneladas/peso se "reais" ou "r$" também aparecer no texto.
    pediu_toneladas = "toneladas" in colunas_metricas or "peso_liquido" in colunas_metricas
    mencionou_reais = "real" in texto_lower or "r$" in texto_lower

    if pediu_toneladas and not mencionou_reais and "faturamento" in colunas_metricas:
        colunas_metricas.remove("faturamento")

    # Caso especial: "meta de tonelada" pode existir por RCA e por
    # filial ao mesmo tempo nos dados. Escolhe a coluna certa conforme
    # o que a resposta menciona, em vez de mostrar as duas juntas.
    tem_meta_rca = "meta_tonelada_rca" in df.columns
    tem_meta_filial = "meta_tonelada_filial" in df.columns

    if "meta" in texto_lower and "tonelada" in texto_lower and (tem_meta_rca or tem_meta_filial):
        if "rca" in texto_lower or "vendedor" in texto_lower:
            colunas_metricas = [c for c in ("meta_tonelada_rca",) if c in df.columns]
        elif "filial" in texto_lower:
            colunas_metricas = [c for c in ("meta_tonelada_filial",) if c in df.columns]
        else:
            colunas_metricas = [
                c for c in ("meta_tonelada_rca", "meta_tonelada_filial")
                if c in df.columns
            ]

    # Se nenhuma palavra bateu com nenhuma métrica conhecida, mostra
    # só as colunas de IDENTIFICAÇÃO (nome, código, filial, período) —
    # nunca despeja valores/métricas que ninguém pediu. Isso cobre
    # perguntas tipo "liste os RCAs", que não pedem nenhum número.
    if not colunas_metricas:
        colunas_metricas = []

    # Se os dados trazem a variação em relação ao mês/ano anterior,
    # inclui essa coluna automaticamente — é sempre relevante quando
    # presente, não depende de palavra-chave na pergunta.
    if "percentual_mes_anterior" in df.columns and "percentual_mes_anterior" not in colunas_metricas:
        colunas_metricas.append("percentual_mes_anterior")

    if "percentual_ano_anterior" in df.columns and "percentual_ano_anterior" not in colunas_metricas:
        colunas_metricas.append("percentual_ano_anterior")

    df = df[colunas_base + colunas_metricas].copy()

    if "mes" in df.columns:
        df["mes"] = df["mes"].map(MESES_PT).fillna(df["mes"])

    for coluna in colunas_metricas:
        if coluna in COLUNAS_MONETARIAS:
            df[coluna] = df[coluna].apply(formatar_moeda)
        elif coluna in ("percentual_mes_anterior", "percentual_ano_anterior"):
            df[coluna] = df[coluna].apply(formatar_percentual_com_sinal)

    # Troca valores vazios (None/NaN) por um texto claro, pra não
    # aparecer "None" nem um traço confuso de se enxergar na tela.
    df = df.fillna("sem dados")

    df = df.rename(columns=RENOMEAR_COLUNAS)

    return df


def descrever_periodo(dados_tabela, texto_referencia):
    """
    Tenta descobrir o(s) ano(s) envolvido(s) pra mostrar como legenda
    acima da tabela — primeiro olhando os próprios dados, depois como
    último recurso procurando um ano escrito na pergunta.
    """
    if dados_tabela and "ano_1" in dados_tabela[0]:
        ano_1 = dados_tabela[0]["ano_1"]
        ano_2 = dados_tabela[0]["ano_2"]
        return f"Comparando: {ano_1} vs {ano_2}"

    anos_nos_dados = sorted({
        item.get("ano")
        for item in dados_tabela
        if isinstance(item, dict) and item.get("ano")
    })

    if len(anos_nos_dados) == 1:
        return f"Ano: {anos_nos_dados[0]}"

    if len(anos_nos_dados) > 1:
        return f"Anos: {', '.join(str(ano) for ano in anos_nos_dados)}"

    anos_completos = re.findall(r"\b(?:19|20)\d{2}\b", texto_referencia)
    if anos_completos:
        return f"Ano: {', '.join(sorted(set(anos_completos)))}"

    return None


COLUNAS_DE_IDENTIFICACAO = {
    "Filial", "RCA", "Código", "Código RCA", "Ano", "Mês",
}


def vale_a_pena_mostrar_tabela(dados_tabela, texto_referencia):
    """
    Decide se a tabela agrega algo além do texto. Duas condições
    precisam ser verdadeiras ao mesmo tempo:
    1. Ter pelo menos uma coluna de valor/métrica (não só
       identificação como nome, código, filial...);
    2. Sobrar mais de 1 linha DEPOIS de qualquer filtro (ex: quando a
       pergunta é "qual filial teve o maior NPS", a tabela é filtrada
       pra só a vencedora — se sobra 1 linha só, é a mesma coisa que
       um valor único, e o texto já basta).
    """
    tabela = preparar_tabela(dados_tabela, texto_referencia)

    if len(tabela) <= 1:
        return False

    colunas_de_valor = [
        coluna for coluna in tabela.columns
        if coluna not in COLUNAS_DE_IDENTIFICACAO
    ]
    return len(colunas_de_valor) > 0


def exibir_tabela(dados_tabela, texto_referencia, chave):
    """Renderiza a tabela formatada + botão de download em Excel."""
    legenda = descrever_periodo(dados_tabela, texto_referencia)
    if legenda:
        st.caption(legenda)

    tabela = preparar_tabela(dados_tabela, texto_referencia)

    # Converte tudo pra texto antes de exibir — evita erro do pyarrow
    # quando uma coluna mistura números com texto (ex: NPS com valor
    # numérico em alguns meses e "sem dados" em outros). O Excel
    # (mais abaixo) continua usando os dados originais, sem essa
    # conversão.
    tabela_exibicao = tabela.astype(str)

    # st.table é uma tabela estática, sem barra de ferramentas — não
    # tem botão de tela cheia nem de baixar CSV, evitando os problemas
    # de layout que apareciam com st.dataframe.
    st.table(tabela_exibicao.set_index(tabela_exibicao.columns[0]))

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        tabela.to_excel(writer, index=False, sheet_name="Dados")

    st.download_button(
        label="⬇️ Baixar em Excel",
        data=buffer.getvalue(),
        file_name="resultado.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument"
            ".spreadsheetml.sheet"
        ),
        key=f"download_{chave}",
    )


# Cores da marca Ferronorte, usadas nos acentos visuais do app.
AZUL_FERRONORTE = "#0E5EA6"
LARANJA_FERRONORTE = "#F18325"
VERDE_FERRONORTE = "#349959"

CAMINHO_ICONE = "assets/icone_ferronorte.png"

AVATAR_POR_PAPEL = {"user": "🧑‍💼", "assistant": CAMINHO_ICONE}

st.set_page_config(
    page_title="Chatbot Comercial Ferronorte",
    page_icon=CAMINHO_ICONE,
    layout="centered",
)
_icone_base64 = base64.b64encode(Path(CAMINHO_ICONE).read_bytes()).decode()

st.markdown(
    f"""
    <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 4px;">
        <img src="data:image/png;base64,{_icone_base64}" style="width: 64px; flex-shrink: 0;">
        <div style="line-height: 1.35;">
            <div style="font-size: 1.25rem; font-weight: 700;">Olá! 👋</div>
            <div style="font-size: 0.9rem; opacity: 0.75;">
                Sou seu assistente virtual. Como posso te ajudar?
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <style>
    .badge-indicador {{
        display: inline-block;
        padding: 2px 10px 2px 8px;
        margin: 2px 4px 2px 0;
        border-radius: 999px;
        font-size: 0.8rem;
        background-color: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-left: 3px solid var(--cor-indicador, {AZUL_FERRONORTE});
    }}
    .legenda-filtros {{
        font-size: 0.8rem;
        opacity: 0.6;
        margin-top: 4px;
    }}
    </style>
    <div style="opacity: 0.75; font-size: 0.85rem; margin-bottom: 4px;">
        No momento posso ajudar com consultas de:
    </div>
    <span class="badge-indicador" style="--cor-indicador: {AZUL_FERRONORTE};">💰 Faturamento (R$ e toneladas — anual, mensal e diário) — 2020 a 2025</span>
    <span class="badge-indicador" style="--cor-indicador: {LARANJA_FERRONORTE};">🎯 Metas (faturamento) — 2020 a 2025</span>
    <span class="badge-indicador" style="--cor-indicador: {LARANJA_FERRONORTE};">🎯 Metas (tonelada) — 2024 a 2026</span>
    <span class="badge-indicador" style="--cor-indicador: {VERDE_FERRONORTE};">⭐ NPS</span>
    <div class="legenda-filtros">
        Tudo por <b>filial, RCA, supervisor ou período</b>, além da
        lista de filiais.
    </div>
    """,
    unsafe_allow_html=True,
)

if "mensagens" not in st.session_state:
    st.session_state.mensagens = []

if "pergunta_sugerida" not in st.session_state:
    st.session_state.pergunta_sugerida = None

with st.sidebar:
    with st.container(border=True, key="painel_perguntas"):
        st.markdown(
            """
            <style>
            .st-key-painel_perguntas button[kind="secondary"] {
                text-align: left;
                border-radius: 10px;
                padding: 0.6rem 0.85rem;
                background-color: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                transition: background-color 0.15s ease;
                font-size: 0.88rem;
            }
            .st-key-painel_perguntas button[kind="secondary"]:hover {
                background-color: rgba(14, 94, 166, 0.15);
                border-color: #0E5EA6;
                color: #F8F8F7;
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
                border-top: 1px solid rgba(255, 255, 255, 0.08);
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("#### 💡 Experimente perguntar")
        st.caption("Um exemplo por indicador. Clique para ver no chat.")

        for indice, item in enumerate(PERGUNTAS_NORTEADORAS):
            st.markdown(
                f'<div class="rotulo-indicador">{item["categoria"]}</div>',
                unsafe_allow_html=True,
            )

            if st.button(
                item["pergunta"],
                key=f"norteadora_{indice}",
                use_container_width=True,
            ):
                if item["resposta"] is None:
                    st.session_state.pergunta_sugerida = item["pergunta"]
                else:
                    st.session_state.mensagens.append(
                        {"papel": "user", "conteudo": item["pergunta"]}
                    )
                    st.session_state.mensagens.append(
                        {
                            "papel": "assistant",
                            "conteudo": item["resposta"],
                            "dados_tabela": None,
                        }
                    )

            resposta_previa = item["resposta"] or "Busca o dado atualizado na hora do clique."
            st.caption(
                escapar_para_markdown(resposta_previa),
                unsafe_allow_html=True,
            )

            if indice < len(PERGUNTAS_NORTEADORAS) - 1:
                st.markdown(
                    '<hr class="separador-indicador">', unsafe_allow_html=True
                )

for indice_mensagem, mensagem in enumerate(st.session_state.mensagens):
    with st.chat_message(
        mensagem["papel"], avatar=AVATAR_POR_PAPEL.get(mensagem["papel"])
    ):
        st.text(mensagem["conteudo"])

        if mensagem.get("dados_tabela") and vale_a_pena_mostrar_tabela(
            mensagem["dados_tabela"], mensagem.get("conteudo", "")
        ):
            with st.expander("📊 Ver como tabela"):
                exibir_tabela(
                    mensagem["dados_tabela"],
                    mensagem.get("conteudo", ""),
                    chave=f"historico_{indice_mensagem}",
                )

pergunta = st.chat_input(
    "Digite sua pergunta sobre algum indicador comercial..."
)

if not pergunta and st.session_state.pergunta_sugerida:
    pergunta = st.session_state.pergunta_sugerida
    st.session_state.pergunta_sugerida = None

if pergunta:
    registrar_pergunta(pergunta)

    st.session_state.mensagens.append(
        {
            "papel": "user",
            "conteudo": pergunta,
        }
    )

    with st.chat_message("user", avatar=AVATAR_POR_PAPEL["user"]):
        st.markdown(pergunta)

    historico = [
        mensagem
        for mensagem in st.session_state.mensagens[:-1]
    ]

    with st.chat_message("assistant", avatar=AVATAR_POR_PAPEL["assistant"]):
        placeholder = st.empty()
        placeholder.markdown(
            """
            <div class="digitando">
                <span></span><span></span><span></span>
            </div>
            <style>
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
            </style>
            """,
            unsafe_allow_html=True,
        )

        # A bolha de "digitando" é sempre substituída pelo conteúdo
        # final, seja a resposta ou o erro — nunca fica travada na tela.
        try:
            resposta, dados_tabela = processar_pergunta(
                pergunta=pergunta,
                historico=historico,
            )
            placeholder.text(resposta)

            if dados_tabela and vale_a_pena_mostrar_tabela(dados_tabela, resposta):
                with st.expander("📊 Ver como tabela"):
                    exibir_tabela(
                        dados_tabela,
                        resposta,
                        chave="atual",
                    )

            st.session_state.mensagens.append(
                {
                    "papel": "assistant",
                    "conteudo": resposta,
                    "dados_tabela": dados_tabela,
                }
            )

        except ChatbotError as error:
            mensagem_erro = str(error)
            placeholder.error(mensagem_erro)

            st.session_state.mensagens.append(
                {
                    "papel": "assistant",
                    "conteudo": mensagem_erro,
                }
            )

            logger.warning("Erro ao processar pergunta: %s", error)

        except Exception as error:
            mensagem_erro = str(error)
            placeholder.error(mensagem_erro)

            st.session_state.mensagens.append(
                {
                    "papel": "assistant",
                    "conteudo": mensagem_erro,
                }
            )

            logger.exception("Erro inesperado ao processar pergunta")