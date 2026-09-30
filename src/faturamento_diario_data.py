"""
Carregamento e preparação dos dados de Faturamento por dia.

O CSV (`faturamento_diario.csv`) funciona como um cache em disco: se
tiver menos de 1 hora, é só lido; se estiver mais velho (ou não
existir ainda), o Oracle é consultado de novo e o CSV é reescrito antes
de ler — mesmo mecanismo do faturamento mensal (`faturamento_data.py`).

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
import time
from datetime import date
from pathlib import Path

import pandas as pd

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
_SEGUNDOS_CACHE = 3600
_TENTATIVAS_ORACLE = 3
_SEGUNDOS_ENTRE_TENTATIVAS = 5

# Colunas que src/faturamento_diario_data.py e src/catalogo.py de fato
# leem desse arquivo — nada além disso precisa ser gerado.
COLUNAS_SAIDA = [
    "CODFILIAL", "DATA", "COD_RCA", "NOME_RCA",
    "VENDA_BRUTA", "VALORDESC", "VENDA_LIQ", "QT_NOTAS",
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
               ROUND(SUM(VLDESCONTO), 2) VALORDESC
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


def _gravar_csv(tabela: pd.DataFrame) -> None:
    ARQUIVO_FATURAMENTO_DIARIO.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_csv(
        ARQUIVO_FATURAMENTO_DIARIO, sep=";", encoding="latin1", decimal=",", index=False,
    )


def _gravar_csv_cobranca(tabela: pd.DataFrame) -> None:
    ARQUIVO_FATURAMENTO_DIARIO_FORMA_PAGAMENTO.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_csv(
        ARQUIVO_FATURAMENTO_DIARIO_FORMA_PAGAMENTO, sep=";", encoding="latin1", decimal=",",
        index=False,
    )


def _atualizar_se_necessario() -> None:
    """
    Mantém `ARQUIVO_FATURAMENTO_DIARIO` com no máximo 1 hora de idade. Se o Oracle
    estiver fora do ar, tenta de novo algumas vezes antes de desistir e
    seguir usando o CSV que já existe (mesmo desatualizado) — melhor
    responder com um dado velho do que não responder nada. Se o
    arquivo nem existe ainda e o Oracle não responde, a falha sobe (não
    tem o que servir).
    """
    if ARQUIVO_FATURAMENTO_DIARIO.exists():
        idade = time.time() - ARQUIVO_FATURAMENTO_DIARIO.stat().st_mtime
        if idade < _SEGUNDOS_CACHE:
            return

    ultimo_erro = None
    for tentativa in range(1, _TENTATIVAS_ORACLE + 1):
        try:
            tabela = gerar_tabela()
            _gravar_csv(tabela)
            return
        except Exception as erro:
            ultimo_erro = erro
            logger.warning(
                "Falha ao atualizar faturamento diário do Oracle "
                f"(tentativa {tentativa}/{_TENTATIVAS_ORACLE}): {erro}"
            )
            if tentativa < _TENTATIVAS_ORACLE:
                time.sleep(_SEGUNDOS_ENTRE_TENTATIVAS)

    if ARQUIVO_FATURAMENTO_DIARIO.exists():
        logger.warning(
            "Não foi possível atualizar o faturamento diário — "
            "seguindo com o CSV existente (pode estar desatualizado)."
        )
        return

    raise ultimo_erro


def _atualizar_cobranca_se_necessario() -> None:
    """
    Mesma lógica de `_atualizar_se_necessario`, pro arquivo de forma de
    pagamento (`ARQUIVO_FATURAMENTO_DIARIO_FORMA_PAGAMENTO`).
    """
    if ARQUIVO_FATURAMENTO_DIARIO_FORMA_PAGAMENTO.exists():
        idade = time.time() - ARQUIVO_FATURAMENTO_DIARIO_FORMA_PAGAMENTO.stat().st_mtime
        if idade < _SEGUNDOS_CACHE:
            return

    ultimo_erro = None
    for tentativa in range(1, _TENTATIVAS_ORACLE + 1):
        try:
            tabela = gerar_tabela_cobranca()
            _gravar_csv_cobranca(tabela)
            return
        except Exception as erro:
            ultimo_erro = erro
            logger.warning(
                "Falha ao atualizar forma de pagamento do Oracle "
                f"(tentativa {tentativa}/{_TENTATIVAS_ORACLE}): {erro}"
            )
            if tentativa < _TENTATIVAS_ORACLE:
                time.sleep(_SEGUNDOS_ENTRE_TENTATIVAS)

    if ARQUIVO_FATURAMENTO_DIARIO_FORMA_PAGAMENTO.exists():
        logger.warning(
            "Não foi possível atualizar a forma de pagamento — "
            "seguindo com o CSV existente (pode estar desatualizado)."
        )
        return

    raise ultimo_erro


def _carregar_csv_8302(caminho: Path) -> pd.DataFrame:
    if not caminho.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {caminho}"
        )

    dados = pd.read_csv(
        caminho,
        sep=";",
        encoding="latin1",
        decimal=",",
    )

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
    Carrega o faturamento diário, atualizando do Oracle primeiro se o
    CSV estiver com mais de 1 hora (ver `_atualizar_se_necessario`).
    """
    _atualizar_se_necessario()
    return _carregar_csv_8302(ARQUIVO_FATURAMENTO_DIARIO)


def carregar_faturamento_diario_forma_pagamento() -> pd.DataFrame:
    """
    Carrega o faturamento diário agrupado por forma de pagamento,
    usado SOMENTE quando a pergunta filtra/agrupa por forma de
    pagamento — o arquivo principal (ARQUIVO_FATURAMENTO_DIARIO) não tem essa
    granularidade. Atualiza do Oracle primeiro se o CSV estiver com
    mais de 1 hora (mesmo mecanismo do arquivo principal).
    """
    _atualizar_cobranca_se_necessario()
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
