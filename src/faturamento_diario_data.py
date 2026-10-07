"""
Carregamento e preparação dos dados de Faturamento por dia.

O CSV (`faturamento_diario.csv`) funciona como um cache em disco,
atualizado em segundo plano por `src/atualizador.py` — mesmo mecanismo
do faturamento mensal (ver `src/arquivos_oracle.py`).

Fonte dos dados (Oracle, schema FNORTE, só leitura — ver
docs/arquitetura_atual.md):
- Venda (bruta, desconto, nº de notas), nome do RCA: `GFN_MVIEW_VENDAS_ATUAL`.
- Devolução: `VIEW_DEVOL_RESUMO_FATURAMENTO`.

Forma de pagamento (`faturamento_diario_forma_pagamento.csv`, usado só
quando a pergunta filtra/agrupa por forma de pagamento — ver
`carregar_faturamento_diario_forma_pagamento`): mesmas duas fontes acima, cada
uma já tem a coluna `CODCOB` — agrupar por ela também (com `PCCOB` pro
nome) reproduz exatamente o valor por forma de pagamento, incluindo a
devolução (validado nos 2 anos que o CSV antigo cobria, 0 de
diferença).
"""
from datetime import date
from pathlib import Path

import pandas as pd

from src.arquivos_oracle import (
    garantir,
    gravar_csv,
    inicio_da_janela_parcial,
    ler_csv,
)
from src.connection import get_connection
from src.filiais import padronizar_filiais
from src.filial_utils import (
    encontrar_filial_mais_proxima,
    normalizar_nome_filial,
)
from src.logger import obter_logger

logger = obter_logger(__name__)

RAIZ_PROJETO = Path(__file__).resolve().parent.parent

ARQUIVO_FATURAMENTO_DIARIO = (
    RAIZ_PROJETO
    / "dados"
    / "faturamento_diario.csv"
)

ARQUIVO_FATURAMENTO_DIARIO_FORMA_PAGAMENTO = (
    RAIZ_PROJETO
    / "dados"
    / "faturamento_diario_forma_pagamento.csv"
)

DESDE_PADRAO = date(2020, 1, 1)

# Colunas que src/faturamento_diario_data.py e src/catalogo.py de fato
# leem desse arquivo — nada além disso precisa ser gerado.
COLUNAS_SAIDA = [
    "CODFILIAL", "DATA", "COD_RCA", "NOME_RCA",
    "VENDA_BRUTA", "VALORDESC", "VENDA_LIQ", "QT_NOTAS", "VENDA_TABELA",
]

COLUNAS_SAIDA_COBRANCA = [
    "CODFILIAL", "DATA", "COD_RCA", "COBRANCA",
    "VENDA_BRUTA", "VALORDESC", "VENDA_LIQ", "QT_NOTAS",
]


def _consultar_vendas(cursor, desde: date) -> pd.DataFrame:
    cursor.execute(
        """
        SELECT CODFILIAL, TRUNC(DTMOV) DATA, CODUSUR,
               MAX(NOME) NOME_RCA,
               COUNT(DISTINCT NUMTRANSVENDA) QT_NOTAS,
               ROUND(SUM(VLVENDA), 2) VENDA_BRUTA,
               ROUND(SUM(VLTABELA), 2) VENDA_TABELA,
               ROUND(SUM(VLDESCONTO), 4) VALORDESC
        FROM GFN_MVIEW_VENDAS_ATUAL
        WHERE DTMOV >= :desde
        GROUP BY CODFILIAL, TRUNC(DTMOV), CODUSUR
        """,
        desde=desde,
    )
    colunas = [d[0] for d in cursor.description]
    return pd.DataFrame(cursor.fetchall(), columns=colunas)


def _consultar_devolucao(cursor, desde: date) -> pd.DataFrame:
    cursor.execute(
        """
        SELECT CODFILIAL, TRUNC(DTENT) DATA, CODUSUR,
               ROUND(SUM(VLDEVOLUCAO), 2) VALOR_DEV
        FROM VIEW_DEVOL_RESUMO_FATURAMENTO
        WHERE DTENT >= :desde
        GROUP BY CODFILIAL, TRUNC(DTENT), CODUSUR
        """,
        desde=desde,
    )
    colunas = [d[0] for d in cursor.description]
    return pd.DataFrame(cursor.fetchall(), columns=colunas)


def gerar_tabela(desde: date = DESDE_PADRAO) -> pd.DataFrame:
    """
    Busca venda e devolução no Oracle (duas consultas simples, já
    agregadas no banco, por filial/dia/vendedor) e junta em Python —
    ver docstring do módulo pras fontes.
    """
    conexao = get_connection()

    try:
        cursor = conexao.cursor()
        vendas = _consultar_vendas(cursor, desde)
        devolucao = _consultar_devolucao(cursor, desde)
    finally:
        conexao.close()

    chave = ["CODFILIAL", "DATA", "CODUSUR"]
    dados = vendas.merge(devolucao, on=chave, how="left")

    dados["CODFILIAL"] = dados["CODFILIAL"].astype(int)
    dados["VALOR_DEV"] = dados["VALOR_DEV"].fillna(0.0)
    dados["VENDA_LIQ"] = (dados["VENDA_BRUTA"] - dados["VALOR_DEV"]).round(2)

    dados = dados.rename(columns={"CODUSUR": "COD_RCA"})

    return dados[COLUNAS_SAIDA]


def _consultar_vendas_cobranca(cursor, desde: date) -> pd.DataFrame:
    cursor.execute(
        """
        SELECT V.CODFILIAL, TRUNC(V.DTMOV) DATA, V.CODUSUR,
               V.CODCOB, MAX(C.COBRANCA) COBRANCA,
               COUNT(DISTINCT V.NUMTRANSVENDA) QT_NOTAS,
               ROUND(SUM(V.VLVENDA), 2) VENDA_BRUTA,
               ROUND(SUM(V.VLDESCONTO), 2) VALORDESC
        FROM GFN_MVIEW_VENDAS_ATUAL V
        LEFT JOIN PCCOB C ON (C.CODCOB = V.CODCOB)
        WHERE V.DTMOV >= :desde
        GROUP BY V.CODFILIAL, TRUNC(V.DTMOV), V.CODUSUR, V.CODCOB
        """,
        desde=desde,
    )
    colunas = [d[0] for d in cursor.description]
    return pd.DataFrame(cursor.fetchall(), columns=colunas)


def _consultar_devolucao_cobranca(cursor, desde: date) -> pd.DataFrame:
    cursor.execute(
        """
        SELECT CODFILIAL, TRUNC(DTENT) DATA, CODUSUR, CODCOB,
               ROUND(SUM(VLDEVOLUCAO), 2) VALOR_DEV
        FROM VIEW_DEVOL_RESUMO_FATURAMENTO
        WHERE DTENT >= :desde
        GROUP BY CODFILIAL, TRUNC(DTENT), CODUSUR, CODCOB
        """,
        desde=desde,
    )
    colunas = [d[0] for d in cursor.description]
    return pd.DataFrame(cursor.fetchall(), columns=colunas)


def gerar_tabela_cobranca(desde: date = DESDE_PADRAO) -> pd.DataFrame:
    """
    Igual a `gerar_tabela`, mas agrupando também por forma de pagamento
    (`CODCOB`) — usada só quando a pergunta filtra/agrupa por forma de
    pagamento (ver `carregar_faturamento_diario_forma_pagamento`).
    """
    conexao = get_connection()

    try:
        cursor = conexao.cursor()
        vendas = _consultar_vendas_cobranca(cursor, desde)
        devolucao = _consultar_devolucao_cobranca(cursor, desde)
    finally:
        conexao.close()

    chave = ["CODFILIAL", "DATA", "CODUSUR", "CODCOB"]
    dados = vendas.merge(devolucao, on=chave, how="outer")

    dados["CODFILIAL"] = dados["CODFILIAL"].astype(int)
    dados["VENDA_BRUTA"] = dados["VENDA_BRUTA"].fillna(0.0)
    dados["VALORDESC"] = dados["VALORDESC"].fillna(0.0)
    dados["QT_NOTAS"] = dados["QT_NOTAS"].fillna(0).astype(int)
    dados["VALOR_DEV"] = dados["VALOR_DEV"].fillna(0.0)
    dados["VENDA_LIQ"] = (dados["VENDA_BRUTA"] - dados["VALOR_DEV"]).round(2)

    dados = dados.rename(columns={"CODUSUR": "COD_RCA"})

    return dados[COLUNAS_SAIDA_COBRANCA]


def _atualizar_arquivo(arquivo: Path, gerar, completa: bool) -> None:
    """
    Completa: tudo desde 2020. Parcial: busca no Oracle só o mês atual e
    o anterior e junta com os dias mais antigos do CSV que já existe.
    """
    if completa or not arquivo.exists():
        gravar_csv(gerar(), arquivo)
        return

    desde = inicio_da_janela_parcial()
    antigo = ler_csv(arquivo)
    antigo["DATA"] = pd.to_datetime(antigo["DATA"])
    antigo = antigo[antigo["DATA"] < pd.Timestamp(desde)]
    gravar_csv(pd.concat([antigo, gerar(desde)], ignore_index=True), arquivo)


def atualizar(completa: bool) -> None:
    _atualizar_arquivo(ARQUIVO_FATURAMENTO_DIARIO, gerar_tabela, completa)


def atualizar_forma_pagamento(completa: bool) -> None:
    _atualizar_arquivo(
        ARQUIVO_FATURAMENTO_DIARIO_FORMA_PAGAMENTO, gerar_tabela_cobranca, completa
    )


def _carregar_csv_8302(caminho: Path) -> pd.DataFrame:
    if not caminho.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {caminho}"
        )

    dados = ler_csv(caminho)

    dados.columns = dados.columns.str.strip()

    # removendo as colunas vazias criadas durante a exportação
    dados = dados.loc[
        :,
        ~dados.columns.str.startswith("Unnamed")
    ]

    # Os dois arquivos (principal e forma de pagamento) são gerados por
    # nós mesmos, sempre em ISO (AAAA-MM-DD) — sem ambiguidade de
    # dia/mês, não precisa de dayfirst.
    dados["DATA"] = pd.to_datetime(dados["DATA"])

    return padronizar_filiais(dados, dados["CODFILIAL"])


def carregar_faturamento_diario() -> pd.DataFrame:
    """
    Carrega o faturamento diário (CSV atualizado em segundo plano — ver
    `src/arquivos_oracle.garantir`).
    """
    garantir([ARQUIVO_FATURAMENTO_DIARIO], atualizar, "faturamento diário")
    return _carregar_csv_8302(ARQUIVO_FATURAMENTO_DIARIO)


def carregar_faturamento_diario_forma_pagamento() -> pd.DataFrame:
    """
    Carrega o faturamento diário agrupado por forma de pagamento,
    usado SOMENTE quando a pergunta filtra/agrupa por forma de
    pagamento — o arquivo principal (ARQUIVO_FATURAMENTO_DIARIO) não tem essa
    granularidade. Atualizado em segundo plano, como o arquivo
    principal.
    """
    garantir(
        [ARQUIVO_FATURAMENTO_DIARIO_FORMA_PAGAMENTO], atualizar_forma_pagamento,
        "faturamento por forma de pagamento",
    )
    return _carregar_csv_8302(ARQUIVO_FATURAMENTO_DIARIO_FORMA_PAGAMENTO)


def construir_mapa_rca_nome() -> dict[int, str]:
    """
    Constrói um mapa de código do RCA para o nome do vendedor.

    A rotina 8302 é a única fonte que traz o nome do RCA (coluna
    NOME_RCA) — a 8280 só tem o código. Quando o mesmo código
    aparece com nomes diferentes ao longo do tempo, fica o primeiro
    nome encontrado.
    """
    dados = carregar_faturamento_diario()

    pares = (
        dados[["COD_RCA", "NOME_RCA"]]
        .dropna()
        .drop_duplicates(subset="COD_RCA")
    )

    return {
        int(codigo): str(nome).strip()
        for codigo, nome in zip(
            pares["COD_RCA"],
            pares["NOME_RCA"],
        )
    }


def construir_lista_rca() -> list[dict]:
    """
    Constrói uma lista de RCAs com código, nome e filial — usada
    para mostrar candidatos de forma legível quando um nome de RCA
    for ambíguo (o mesmo vendedor pode ter um código diferente em
    cada filial).
    """
    dados = carregar_faturamento_diario()

    pares = (
        dados[["COD_RCA", "NOME_RCA", "FILIAL"]]
        .dropna(subset=["COD_RCA", "NOME_RCA"])
        .drop_duplicates(subset="COD_RCA")
    )

    return [
        {
            "codigo": int(linha["COD_RCA"]),
            "nome": str(linha["NOME_RCA"]).strip(),
            "filial": str(linha["FILIAL"]).strip(),
        }
        for _, linha in pares.iterrows()
    ]


def resolver_codigos_rca(
    nome_ou_codigo: str | int,
    filiais: list[str] | None = None,
) -> list[int]:
    """
    Resolve o(s) código(s) numérico(s) de RCA a partir do que o
    usuário informou — o próprio código, ou o nome do vendedor (a IA
    nem sempre sabe o código, então precisa poder buscar por nome).

    Como existem muitos vendedores, o mesmo nome pode bater com mais
    de um RCA (ex: "André Alves" existe com um código diferente em
    cada filial em que atua):
    - se uma filial foi informada na pergunta, ela é usada pra
      restringir os candidatos automaticamente — é o caso mais
      comum de quem usa o chatbot (gerente perguntando pelo RCA da
      própria loja);
    - se, mesmo assim, sobrar mais de um candidato, uma exceção
      clara é levantada, listando código e filial de cada um, em vez
      de escolher um deles silenciosamente;
    - se NENHUMA filial foi informada, todos os códigos encontrados
      para aquele nome são retornados juntos, para que a consulta
      some o faturamento total desse RCA em todas as filiais em que
      ele aparece — é o comportamento esperado quando o usuário não
      restringe a busca a uma loja específica.

    Quando o código já vem numérico (informado direto pelo usuário,
    ou já resolvido antes), ele é validado contra a base — um código
    inexistente levanta erro imediatamente, em vez de seguir adiante
    e só descobrir lá na frente, quando a consulta não retornar
    nenhum dado, o que faria parecer um problema de período.
    """
    rcas = construir_lista_rca()

    texto = str(nome_ou_codigo).strip()

    if isinstance(nome_ou_codigo, int) or texto.isdigit():
        codigo = (
            nome_ou_codigo
            if isinstance(nome_ou_codigo, int)
            else int(texto)
        )

        if not any(rca["codigo"] == codigo for rca in rcas):
            raise ValueError(
                f"O RCA de código {codigo} não foi encontrado."
            )

        return [codigo]

    nome_procurado = normalizar_nome_filial(texto)

    candidatos = [
        rca
        for rca in rcas
        if nome_procurado in normalizar_nome_filial(rca["nome"])
        or normalizar_nome_filial(rca["nome"]) in nome_procurado
    ]

    if len(candidatos) > 1 and filiais:
        candidatos_na_filial = [
            candidato
            for candidato in candidatos
            if candidato["filial"] in filiais
        ]

        if candidatos_na_filial:
            candidatos = candidatos_na_filial

    if len(candidatos) == 1:
        return [candidatos[0]["codigo"]]

    if len(candidatos) > 1:
        if filiais:
            descricoes = ", ".join(
                f"{candidato['nome']} (código {candidato['codigo']}, "
                f"filial {candidato['filial']})"
                for candidato in candidatos
            )
            raise ValueError(
                f"Encontrei mais de um RCA parecido com "
                f"'{nome_ou_codigo}': {descricoes}. Informe o código "
                "do RCA que deseja consultar."
            )

        # Nenhuma filial foi informada: soma o faturamento de todos
        # os RCAs encontrados com esse nome.
        return [candidato["codigo"] for candidato in candidatos]

    # Nenhuma correspondência direta por substring: tenta por
    # similaridade textual, para tolerar pequenos erros de digitação.
    nome_encontrado = encontrar_filial_mais_proxima(
        nome_procurado,
        [rca["nome"] for rca in rcas],
    )

    if nome_encontrado is not None:
        for rca in rcas:
            if rca["nome"] == nome_encontrado:
                return [rca["codigo"]]

    raise ValueError(
        f"O RCA '{nome_ou_codigo}' não foi encontrado."
    )


def verificar_rca(
    nome_ou_codigo: str | int,
    filiais: list[str] | None = None,
) -> dict:
    """
    Verifica se um RCA (por nome ou código) existe, sem precisar de
    período — usada pra confirmar o RCA antes de pedir o período ao
    usuário, evitando pedir uma informação desnecessária quando o
    RCA nem existe na base.
    """
    try:
        codigos = resolver_codigos_rca(nome_ou_codigo, filiais=filiais)
    except ValueError as error:
        return {
            "encontrado": False,
            "mensagem": str(error),
        }

    mapa_rca_nome = construir_mapa_rca_nome()

    return {
        "encontrado": True,
        "rcas_identificados": [
            f"{mapa_rca_nome.get(codigo, 'nome não identificado')} "
            f"(código {codigo})"
            for codigo in codigos
        ],
    }
