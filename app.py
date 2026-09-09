import io
import re

import streamlit as st
import pandas as pd
from src.chatbot import processar_pergunta
from src.exceptions import ChatbotError
from src.logger import obter_logger
from src.perguntas_log import (
    contar_perguntas_registradas,
    obter_perguntas_frequentes,
    registrar_pergunta,
)

logger = obter_logger(__name__)

PERGUNTAS_EXEMPLO = [
    "Qual o faturamento de Timon em julho de 2025?",
    "Qual o NPS geral da empresa?",
    "Quanto faturamos hoje?",
    "Compare o faturamento de Timon em 2024 e 2025.",
]

QUANTIDADE_MINIMA_PARA_FREQUENTES = 5

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
    "mes": "Mês",
    "ano": "Ano",
    "faturamento": "Faturamento",
    "venda_bruta": "Venda Bruta",
    "valor_desconto": "Desconto",
    "toneladas": "Toneladas",
    "peso_liquido": "Peso Líquido",
    "quantidade_notas": "Qtd. Notas",
    "nps": "NPS",
}


def formatar_moeda(valor):
    """Formata um número no padrão R$ 91.783.909,07."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""

    texto = f"{valor:,.2f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


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

    # Se não tem coluna "ano" pronta mas tem "data_inicial" (formato
    # YYYY-MM-DD), extrai o ano de lá — usado em consultas por
    # filial+período que não passam pelo agrupamento mês a mês.
    if "ano" not in df.columns and "data_inicial" in df.columns:
        df["ano"] = df["data_inicial"].str.slice(0, 4)

    colunas_base = [
        coluna for coluna in ("filial", "ano", "mes") if coluna in df.columns
    ]

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

    # Se nenhuma palavra bateu, mostra todas as colunas de dado
    # (fallback de segurança pra nunca esconder informação sem querer).
    if not colunas_metricas:
        colunas_metricas = [
            coluna for coluna in df.columns if coluna not in colunas_base
        ]

    df = df[colunas_base + colunas_metricas].copy()

    if "mes" in df.columns:
        df["mes"] = df["mes"].map(MESES_PT).fillna(df["mes"])

    for coluna in colunas_metricas:
        if coluna in COLUNAS_MONETARIAS:
            df[coluna] = df[coluna].apply(formatar_moeda)

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


def exibir_tabela(dados_tabela, texto_referencia, chave):
    """Renderiza a tabela formatada + botão de download em Excel."""
    legenda = descrever_periodo(dados_tabela, texto_referencia)
    if legenda:
        st.caption(legenda)

    tabela = preparar_tabela(dados_tabela, texto_referencia)

    # st.table é uma tabela estática, sem barra de ferramentas — não
    # tem botão de tela cheia nem de baixar CSV, evitando os problemas
    # de layout que apareciam com st.dataframe.
    st.table(tabela.set_index(tabela.columns[0]))

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


st.set_page_config(
    page_title="Chatbot Comercial Ferronorte",
    page_icon="🤖",
    layout="centered",
)
st.title("🤖 Chatbot Comercial Ferronorte")

st.caption(
    "Consulte Informações sobre Indicadores Comerciais."
)

if "mensagens" not in st.session_state:
    st.session_state.mensagens = []

if "pergunta_sugerida" not in st.session_state:
    st.session_state.pergunta_sugerida = None

with st.sidebar:
    total_perguntas = contar_perguntas_registradas()

    with st.container(border=True, key="painel_perguntas"):
        if total_perguntas >= QUANTIDADE_MINIMA_PARA_FREQUENTES:
            st.markdown("#### 🔥 Perguntas mais frequentes")
            sugestoes = [
                item["pergunta"]
                for item in obter_perguntas_frequentes(limite=5)
            ]
        else:
            st.markdown("#### 💡 Experimente perguntar")
            sugestoes = PERGUNTAS_EXEMPLO

        st.caption("Clique numa pergunta para enviá-la ao chat.")

        st.markdown(
            """
            <style>
            .st-key-painel_perguntas button[kind="secondary"] {
                text-align: left;
                border-radius: 14px;
                padding: 0.75rem 1rem;
                background-color: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                transition: background-color 0.15s ease;
            }
            .st-key-painel_perguntas button[kind="secondary"]:hover {
                background-color: rgba(255, 255, 255, 0.09);
                border-color: rgba(255, 255, 255, 0.18);
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        for indice, sugestao in enumerate(sugestoes):
            rotulo = f"{sugestao}  ›"

            if st.button(
                rotulo,
                key=f"sugestao_{indice}",
                use_container_width=True,
            ):
                st.session_state.pergunta_sugerida = sugestao

for indice_mensagem, mensagem in enumerate(st.session_state.mensagens):
    with st.chat_message(mensagem["papel"]):
        st.text(mensagem["conteudo"])

        if mensagem.get("dados_tabela"):
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

    with st.chat_message("user"):
        st.markdown(pergunta)

    historico = [
        mensagem
        for mensagem in st.session_state.mensagens[:-1]
    ]

    with st.chat_message("assistant"):
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

            if dados_tabela:
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