"""
Formatação do que aparece na tela, sem Streamlit: R$, %, nomes das
colunas e a montagem da tabela (quais colunas, formato e layout).
Funções puras — testadas em tests/test_app.py.
"""
import re

import pandas as pd

from config.constants import MESES_PT
from core.motor import catalogo


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


# Configuração de tabela por ferramenta — fonte única de verdade sobre
# as colunas de valor: nome do campo, "tipo" (usado pra formatação,
# veja FORMATADORES_POR_TIPO), rótulo de exibição, e quando a coluna
# deve aparecer. Hoje só existe "consultar_dados_comerciais", e as
# colunas dela vêm do catalogo.py (campo "exibicao" de cada indicador)
# — um indicador novo não exige editar nada aqui.
#
# Cada coluna tem "sempre": True (aparece sempre que presente, usado
# quando os números sempre andam juntos, ex: meta/realizado/
# atingimento) OU "palavras": [...] (só aparece se uma dessas palavras
# estiver na resposta — evita mostrar dado que ninguém pediu).
#
# "rotulo" pode usar "{ano}" e/ou "{ano_anterior}" como placeholder —
# preparar_tabela troca pelo ano de verdade quando esses campos vêm
# nos dados.
CONFIG_TABELA_POR_FERRAMENTA = {
    "consultar_dados_comerciais": {
        "colunas": catalogo.gerar_colunas_tabela(),
    },
}


def selecionar_colunas_metricas(nome_ferramenta, texto_lower, colunas_disponiveis):
    """
    Decide quais colunas de valor entram na tabela, usando a
    configuração da ferramenta que gerou o resultado (veja
    CONFIG_TABELA_POR_FERRAMENTA). Ferramentas sem configuração (ex:
    listar_filiais) não têm coluna de valor — a tabela fica só com as
    colunas de identificação.
    """
    config = CONFIG_TABELA_POR_FERRAMENTA.get(nome_ferramenta, {})

    colunas = []

    for especificacao in config.get("colunas", []):
        coluna = especificacao["coluna"]

        if coluna not in colunas_disponiveis:
            continue

        bateu_palavra = any(
            palavra in texto_lower
            for palavra in especificacao.get("palavras", [])
        )

        if especificacao.get("sempre") or bateu_palavra:
            colunas.append(coluna)

    return colunas

# Tipo de cada coluna (pra formatação) e rótulo de exibição, derivados
# da config acima — nenhuma ferramenta precisa ser listada duas vezes.
TIPO_POR_COLUNA = {
    especificacao["coluna"]: especificacao["tipo"]
    for config in CONFIG_TABELA_POR_FERRAMENTA.values()
    for especificacao in config.get("colunas", [])
}
# "percentual_mes_anterior"/"percentual_ano_anterior" não pertencem a
# uma ferramenta específica — podem aparecer no resultado de qualquer
# ferramenta agrupada por mês/ano, então têm o tipo registrado à parte.
TIPO_POR_COLUNA["percentual_mes_anterior"] = "percentual_com_sinal"
TIPO_POR_COLUNA["percentual_ano_anterior"] = "percentual_com_sinal"

# Nome/CNPJ/cidade que acompanham uma dimensão (ex: cliente) — vêm do
# catálogo, não de uma lista escrita aqui.
ATRIBUTOS_DA_TABELA = {
    campo: rotulo
    for atributos in catalogo.ATRIBUTOS_DIMENSAO.values()
    for campo, (_, rotulo) in atributos.items()
}

RENOMEAR_COLUNAS = {
    **ATRIBUTOS_DA_TABELA,
    "cliente": "Código Cliente",
    "produto": "Código Produto",
    "familia": "Família",
    "grupo": "Grupo",
    "supervisor": "Código Supervisor",
    "filial": "Filial",
    "estado": "Estado",
    "rca_nome": "RCA",
    "rca": "Código RCA",
    "codigo": "Código",
    "mes": "Mês",
    "ano": "Ano",
    "periodo": "Período",
    "forma_pagamento": "Forma de Pagamento",
    "dia": "Dia",
    "percentual_mes_anterior": "Variação (mês anterior)",
    "percentual_ano_anterior": "Variação (ano anterior)",
    **{
        especificacao["coluna"]: especificacao["rotulo"]
        for config in CONFIG_TABELA_POR_FERRAMENTA.values()
        for especificacao in config.get("colunas", [])
    },
}


def formatar_moeda(valor):
    """Formata um número no padrão R$ 91.783.909,07."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return "sem dados"

    texto = f"{valor:,.2f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def formatar_moeda_com_sinal(valor):
    """Diferença em R$ com sinal: +R$ 14.287.298,37 / −R$ 963.253,53."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return "sem dados"

    sinal = "+" if valor >= 0 else "−"
    return sinal + formatar_moeda(abs(valor))


def formatar_percentual_com_sinal(valor):
    """Formata um percentual com sinal + explícito (ex: +5,64%)."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return "sem dados"

    sinal = "+" if valor >= 0 else ""
    return f"{sinal}{valor:.2f}%".replace(".", ",")


def formatar_percentual_atingimento(valor):
    """Formata o percentual de atingimento de meta (ex: 122,37%)."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return "sem dados"

    # Ex: desconto de R$ 17,17 sobre R$ 500 mil — "0,00%" parecia zero.
    if 0 < abs(valor) < 0.005:
        return "menos de 0,01%"

    return f"{valor:.2f}%".replace(".", ",")


def formatar_numero_com_sinal(valor):
    """Diferença entre dois números, com sinal explícito (ex: +4,43)."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return "sem dados"

    texto = f"{valor:+,.2f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


# Formatador de cada "tipo" declarado em CONFIG_TABELA_POR_FERRAMENTA.
# Colunas do tipo "texto" (ou sem tipo registrado) não passam por
# nenhum formatador — ficam com o valor cru.
FORMATADORES_POR_TIPO = {
    "moeda": formatar_moeda,
    "moeda_com_sinal": formatar_moeda_com_sinal,
    "percentual": formatar_percentual_atingimento,
    "percentual_com_sinal": formatar_percentual_com_sinal,
    "numero_com_sinal": formatar_numero_com_sinal,
}


def formatar_coluna_numerica(serie):
    """
    Números em português (vírgula decimal, ponto de milhar) pra colunas de
    tipo "texto": sem casas decimais quando todos os valores são inteiros
    (contagens), com 2 casas nos demais. Vazio vira "sem dados".
    """
    validos = serie.dropna()
    casas = 0 if (validos % 1 == 0).all() else 2

    def formatar(valor):
        if pd.isna(valor):
            return "sem dados"

        texto = f"{valor:,.{casas}f}"
        return texto.replace(",", "X").replace(".", ",").replace("X", ".")

    return serie.map(formatar)


# Colunas que identificam a linha (em vez de medir alguma coisa).
DIMENSOES_DA_TABELA = (
    "estado", "filial", "rca_nome", "rca", "supervisor", "codigo", "cliente",
    "grupo", "familia", "produto",
    "empresa", *ATRIBUTOS_DA_TABELA, "ano", "mes", "periodo",
    "forma_pagamento", "dia",
)
DIMENSOES_DE_TEMPO = ("ano", "mes", "dia", "periodo")

# Um pivô que gerasse mais colunas que isso ficaria ilegível — nesse caso
# a tabela continua comprida (uma linha por combinação).
LIMITE_COLUNAS_PIVO = 12


def _pivotar(tabela, dimensoes, metricas, metrica_sem_prefixo=None):
    """
    Regra ÚNICA de layout, valha pra qual pergunta for: quando sobram duas
    ou mais dimensões que variam (ex: filial e mês), a que tem MENOS valores
    distintos vira colunas (empate: a de tempo) e as outras ficam nas linhas
    — 2 filiais x 6 meses vira "Mês | FILIAL A | FILIAL B", 18 filiais x
    2 anos vira "Filial | 2024 | 2025". Com mais de uma métrica, cada coluna
    fica "VALOR — Métrica" (a `metrica_sem_prefixo`, quando há, fica só
    "VALOR" e a variação vem ao lado). As colunas ficam agrupadas por
    MÉTRICA — o valor de todos os itens comparados lado a lado primeiro
    (LOURIVAL | SANTA INÊS), depois as demais métricas — pra comparar sem
    pular colunas. Coluna toda vazia (ex: variação do primeiro ano) some.
    Se passar de LIMITE_COLUNAS_PIVO colunas, não pivota. Também não
    pivota quando a maioria das células ficaria vazia (ex: 5 pares RCA x
    cliente, cada cliente de um RCA só — virar os RCAs em colunas deixava
    quase tudo "sem dados").
    """
    # Nome/CNPJ/cidade acompanham a linha do cliente — nunca viram coluna.
    variaveis = [
        d for d in dimensoes
        if d not in ATRIBUTOS_DA_TABELA.values() and tabela[d].nunique() > 1
    ]

    if len(variaveis) < 2 or not metricas:
        return tabela

    pivo = min(
        variaveis,
        key=lambda d: (tabela[d].nunique(), d not in {RENOMEAR_COLUNAS[c] for c in DIMENSOES_DE_TEMPO}),
    )

    if tabela[pivo].nunique() * len(metricas) > LIMITE_COLUNAS_PIVO:
        return tabela

    dimensoes_linha = [d for d in dimensoes if d != pivo]

    celulas = tabela[dimensoes_linha].drop_duplicates().shape[0] * tabela[pivo].nunique()

    if len(tabela) < celulas / 2:
        return tabela

    def nome_da_coluna(valor, metrica):
        if len(metricas) == 1 or metrica == metrica_sem_prefixo:
            return str(valor)

        return f"{valor} — {metrica}"

    linhas: dict = {}

    for _, item in tabela.iterrows():
        chave = tuple(item[d] for d in dimensoes_linha)
        linha = linhas.setdefault(chave, dict(zip(dimensoes_linha, chave)))

        for metrica in metricas:
            linha[nome_da_coluna(item[pivo], metrica)] = (
                item[metrica] if item[metrica] != "" else "sem dados"
            )

    ordem = [
        nome_da_coluna(valor, metrica)
        for metrica in metricas
        for valor in tabela[pivo].unique()
    ]
    resultado = pd.DataFrame(list(linhas.values())).fillna("sem dados")
    resultado = resultado[dimensoes_linha + ordem]
    vazias = [
        c for c in ordem if (resultado[c] == "sem dados").all()
    ]

    return resultado.drop(columns=vazias)


def preparar_tabela(dados_tabela, texto_referencia, nome_ferramenta=None):
    """
    Monta a tabela pronta pra exibição, com uma regra só pra qualquer
    pergunta:
    1. Colunas de valor: as que a consulta pediu ("_colunas_pedidas",
       recortadas pelo motor — veja orquestrador._linhas_da_tabela) e a
       comparação delas; sem isso, o padrão do catálogo (CONFIG_TABELA_
       POR_FERRAMENTA: "sempre" ou por palavra na resposta).
    2. Formatação pelo tipo da coluna (moeda, percentual, número).
    3. Layout: veja _pivotar.
    """
    df = pd.DataFrame(dados_tabela)

    pedidas = None
    rotulos = {}

    if "_colunas_pedidas" in df.columns:
        pedidas = df["_colunas_pedidas"].iloc[0]
        df = df.drop(columns="_colunas_pedidas")

    if "_rotulos" in df.columns:
        rotulos = df["_rotulos"].iloc[0]
        df = df.drop(columns="_rotulos")

    # Valores pra preencher os placeholders "{ano}"/"{ano_anterior}"
    # que um "rotulo" de CONFIG_TABELA_POR_FERRAMENTA pode usar —
    # capturados AQUI, antes de qualquer corte de coluna, porque
    # "ano_anterior" não é uma coluna exibida, só serve pra isso.
    valores_para_rotulo = {}
    for campo in ("ano", "ano_anterior"):
        if campo in df.columns and df[campo].nunique() == 1:
            valores_para_rotulo[campo] = df[campo].iloc[0]

    # A tabela mostra tudo o que a consulta trouxe. (Antes ela era cortada
    # pelas filiais/RCAs citados no texto — pensado pra "qual filial teve o
    # maior NPS", que hoje já vem cortado pelo motor via ordenar_por. Numa
    # pergunta de relação, que precisa de todas as filiais, a tabela ficava
    # só com as citadas, e "Parnaíba" no texto não casava com "PARNAIBA".)
    colunas_base = [
        coluna for coluna in DIMENSOES_DA_TABELA if coluna in df.columns
    ]

    # Se já tem o nome do RCA (rca_nome), não precisa mostrar também o
    # código cru (rca) — uma coluna só de identificação é mais limpo.
    if "rca_nome" in colunas_base and "rca" in colunas_base:
        colunas_base.remove("rca")

    # A chave interna da empresa ("03995515") já aparece formatada no
    # "CNPJ (início)".
    if "empresa_nome" in colunas_base and "empresa" in colunas_base:
        colunas_base.remove("empresa")

    if "supervisor_nome" in colunas_base and "supervisor" in colunas_base:
        colunas_base.remove("supervisor")

    # Se só tem UM ano nos dados, tira a coluna "ano" da tabela — ela
    # já aparece na legenda acima ("Ano: 2025"), repetir em toda
    # linha é redundante. Só mantém quando há vários anos misturados.
    if "ano" in colunas_base and df["ano"].nunique() <= 1:
        colunas_base.remove("ano")

    texto_lower = texto_referencia.lower()

    if pedidas is not None:
        colunas_metricas = []

        for coluna in pedidas:
            for nome in (
                coluna, f"{coluna}_anterior", f"diferenca_{coluna}",
                f"percentual_{coluna}",
            ):
                if nome in df.columns and nome not in colunas_metricas:
                    colunas_metricas.append(nome)
    else:
        colunas_metricas = selecionar_colunas_metricas(
            nome_ferramenta, texto_lower, df.columns
        )

        # "Faturamento" às vezes aparece no texto só como nome genérico do
        # indicador (ex: "faturamento em toneladas"), não significando que
        # o valor em R$ também foi pedido. Só mantém a coluna de R$ junto
        # com toneladas/peso se "reais" ou "r$" também aparecer no texto.
        pediu_toneladas = (
            "toneladas" in colunas_metricas or "peso_liquido" in colunas_metricas
        )
        mencionou_reais = "real" in texto_lower or "r$" in texto_lower

        if pediu_toneladas and not mencionou_reais and "faturamento" in colunas_metricas:
            colunas_metricas.remove("faturamento")

    # Se os dados trazem a variação em relação ao mês/ano anterior,
    # inclui essa coluna automaticamente — é sempre relevante quando
    # presente, não depende de palavra-chave na pergunta.
    for nome in ("percentual_mes_anterior", "percentual_ano_anterior"):
        if nome in df.columns and nome not in colunas_metricas:
            colunas_metricas.append(nome)

    df = df[colunas_base + colunas_metricas].copy()

    if "mes" in df.columns:
        df["mes"] = df["mes"].map(MESES_PT).fillna(df["mes"])

    for coluna in colunas_metricas:
        formatador = FORMATADORES_POR_TIPO.get(TIPO_POR_COLUNA.get(coluna))

        if formatador:
            df[coluna] = df[coluna].apply(formatador)
        elif pd.api.types.is_numeric_dtype(df[coluna]):
            df[coluna] = formatar_coluna_numerica(df[coluna])

    def _resolver_rotulo(rotulo):
        if "{" not in rotulo:
            return rotulo
        try:
            return rotulo.format(**valores_para_rotulo)
        except KeyError:
            return rotulo

    mapa_renomear = {
        coluna: _resolver_rotulo(rotulo)
        for coluna, rotulo in RENOMEAR_COLUNAS.items()
    }
    mapa_renomear.update(rotulos)
    df = df.fillna("sem dados").rename(columns=mapa_renomear)

    # Uma métrica só + as variações ao lado: o valor fica com o nome puro
    # da coluna ("2024 | 2025 | 2025 — Variação"), sem repetir a métrica.
    metricas_de_valor = [
        c for c in colunas_metricas
        if c not in ("percentual_mes_anterior", "percentual_ano_anterior")
    ]

    return _pivotar(
        df,
        [mapa_renomear.get(c, c) for c in colunas_base],
        [mapa_renomear.get(c, c) for c in colunas_metricas],
        mapa_renomear.get(metricas_de_valor[0], metricas_de_valor[0])
        if len(metricas_de_valor) == 1 else None,
    )


def descrever_periodo(dados_tabela, texto_referencia):
    """
    Tenta descobrir o(s) ano(s) envolvido(s) pra mostrar como legenda
    acima da tabela — primeiro olhando os próprios dados, depois como
    último recurso procurando um ano escrito na pergunta.
    """
    anos_nos_dados = sorted({
        item.get("ano")
        for item in dados_tabela
        if isinstance(item, dict) and item.get("ano")
    })

    if len(anos_nos_dados) == 1:
        return f"Ano: {anos_nos_dados[0]}"

    if len(anos_nos_dados) > 1:
        return f"Anos: {', '.join(str(ano) for ano in anos_nos_dados)}"

    # Só 20xx (os dados começam em 2020) e nunca um número logo depois de
    # "código" — "AURORA ANDRADE-F01 (código 1901)" virava "Ano: 1901".
    anos_completos = re.findall(
        r"(?<!código )(?<!codigo )\b20\d{2}\b", texto_referencia, flags=re.IGNORECASE
    )
    if anos_completos:
        return f"Ano: {', '.join(sorted(set(anos_completos)))}"

    return None


COLUNAS_DE_IDENTIFICACAO = {
    "Estado", "Filial", "RCA", "Código", "Código RCA", "Código Cliente",
    "Código Supervisor", "Código Produto",
    "Ano", "Mês", "Período", "Forma de Pagamento", "Dia",
    *ATRIBUTOS_DA_TABELA.values(),
}


def vale_a_pena_mostrar_tabela(dados_tabela, texto_referencia, nome_ferramenta=None):
    """
    Decide se a tabela agrega algo além do texto. Duas condições
    precisam ser verdadeiras ao mesmo tempo:
    1. Ter pelo menos uma coluna de valor/métrica (não só
       identificação como nome, código, filial...);
    2. Ter mais de 1 linha (ex: "qual filial teve o maior NPS" já vem
       cortado pelo motor pra só a vencedora — 1 linha só é a mesma
       coisa que um valor único, e o texto já basta).
    """
    tabela = preparar_tabela(dados_tabela, texto_referencia, nome_ferramenta)

    if len(tabela) <= 1:
        return False

    colunas_de_valor = [
        coluna for coluna in tabela.columns
        if coluna not in COLUNAS_DE_IDENTIFICACAO
    ]
    return len(colunas_de_valor) > 0
