"""
Carregamento e preparação dos dados de Faturamento mensal.

O CSV (`faturamento_mensal.csv`) funciona como um cache em disco,
atualizado em segundo plano por `core/services/atualizador_service.py` (completa ao abrir
o chatbot e 1x por dia; parcial — mês atual e anterior — de hora em
hora). Quem pergunta só lê o CSV; ver `core/repositories/arquivos_repository.py`.

Fonte dos dados (Oracle, schema FNORTE, só leitura — ver
docs/arquitetura_atual.md, seção "Investigação: ligar o faturamento no
Oracle"):
- Venda (bruta e de tabela), notas: `VIEW_VENDAS_RESUMO_FATURAMENTO`.
- Peso: `GFN_MVIEW_VENDAS_HIST`/`GFN_MVIEW_VENDAS_ANO_ATUAL`, com a
  correção do bug de KG (ver `_PESO_POR_LINHA`).
- Devolução: `VIEW_DEVOL_RESUMO_FATURAMENTO`.
- Meta: `PCMETARCA`.
"""
from datetime import date
from pathlib import Path

import pandas as pd

from core.repositories.arquivos_repository import (
    antes_da_janela_mensal,
    garantir,
    gravar_csv,
    inicio_da_janela_parcial,
    ler_csv,
)
from core.repositories.oracle import get_connection
from core.repositories.filiais_repository import padronizar_filiais
from core.logger import obter_logger

logger = obter_logger(__name__)

RAIZ_PROJETO = Path(__file__).resolve().parents[2]  # core/repositories/ -> raiz

ARQUIVO_FATURAMENTO_MENSAL = (
    RAIZ_PROJETO
    /"data"
    /"faturamento_mensal.csv"
)

ANO_INICIO_PADRAO = 2020

# Colunas que o código (core/) de fato lê desse arquivo (catalogo.py e
# metas_data.py) — nada além disso precisa ser gerado.
COLUNAS_SAIDA = [
    "CODFILIAL", "ANO", "MES", "COD_RCA", "COD_SUPERVISOR",
    "NOME_SUPERVISOR", "VENDA_BRUTA", "VALORDESC", "VENDA_LIQ",
    "PESOLIQ", "QT_NOTAS", "VALOR_META", "VENDA_TABELA", "CONTA_EMPRESA",
]

# Códigos de RCA que são CONTAS DA EMPRESA, não vendedores (ex:
# "COMERCIAL FERRONORTE LTDA-F09-TIMON", "FERROLESTE F08"): guardam parte
# da meta da filial (a rotina 8139 soma) e, alguns, vendas de balcão.
# Entram na meta/faturamento da filial, mas ficam fora das listas de RCA
# (ver orquestrador._rcas_com_meta_cadastrada).
_NOME_CONTA_EMPRESA = (
    r"COMERCIAL FERRONORTE|FERRONORTE COM DE FERRAGENS|FERROLESTE|"
    r"METALURGICA FERRONORTE"
)

# Mesmos filtros de negócio usados para achar venda válida (nota não
# cancelada, tipo de nota, código fiscal, condição de venda) — validados
# contra o CSV nos 6 anos, batendo exato. Reaproveitados tanto pra venda
# (VIEW_VENDAS_RESUMO_FATURAMENTO) quanto pro peso (GFN_MVIEW_VENDAS_*).
_FILTRO_VENDA_VALIDA = """
      AND DTCANCEL IS NULL
      AND ESPECIE NOT IN ('NS', 'CO')
      AND COALESCE(CODFISCAL, 0) NOT IN (522, 622, 722, 532, 632, 732)
      AND COALESCE(CONDVENDA, -1) IN (-1, 1, 5, 7, 9, 11, 14)
"""

# As duas views de peso (HIST e ANO_ATUAL) têm as mesmas colunas, mas um
# "SELECT *" num UNION ALL junta por POSIÇÃO, não por nome — se a ordem
# das colunas divergir entre as duas views (mesmo com nomes iguais), os
# valores vão parar em colunas erradas em silêncio. Por isso cada lado do
# UNION ALL nomeia as colunas explicitamente.
_COLUNAS_PESO = "DTMOV, CODFILIAL, CODUSUR, TOTPESOLIQ, UNIDADE, QTVENDA"

# Peso: pra produto vendido por peça (UNIDADE != 'KG'), TOTPESOLIQ já é
# quantidade × peso cadastrado do produto — correto. Pra produto vendido
# direto em quilos (UNIDADE = 'KG', ex: chapas de aço), a quantidade JÁ é
# o peso — nesse caso TOTPESOLIQ está multiplicando o peso por ele mesmo
# (bug confirmado no próprio WinThor, não só nessa view: o cabeçalho da
# nota, PCNFSAID.TOTPESOLIQ, tem o mesmo erro). Reduziu a margem de erro
# de 3,17% pra 1,18% no ano de 2025 (ver docs/arquitetura_atual.md).
_PESO_POR_LINHA = "CASE WHEN UNIDADE = 'KG' THEN QTVENDA ELSE TOTPESOLIQ END"


# Desconto (VALORDESC) = desconto concedido, igual à rotina 8302 e ao
# faturamento diário: nesta view, VLDESCONTO vem direto de PCMOV e é o
# desconto POR UNIDADE (preço de tabela − preço vendido, zero quando o
# item sai na tabela ou acima dela) — por isso multiplica pela
# quantidade. Multiplicado, bate centavo a centavo com a 8302 (R$
# 2.259.420,82 em ago/2026). Não é "venda − tabela" (o VALORDESC da 8280):
# essa conta sai negativa e deixa a venda acima da tabela abater o
# desconto dos outros itens.
def _consultar_vendas(cursor, desde: date) -> pd.DataFrame:
    cursor.execute(
        f"""
        SELECT V.CODFILIAL, EXTRACT(YEAR FROM V.DTSAIDA) ANO,
               EXTRACT(MONTH FROM V.DTSAIDA) MES, V.CODUSUR,
               V.CODSUPERVISOR, MAX(S.NOME) NOME_SUPERVISOR,
               COUNT(DISTINCT V.NUMTRANSVENDA) QT_NOTAS,
               ROUND(SUM(V.VLVENDA), 2) VENDA_BRUTA,
               ROUND(SUM(V.VLTABELA), 2) VENDA_TABELA,
               ROUND(SUM(V.VLDESCONTO * V.QT), 2) VALORDESC
        FROM VIEW_VENDAS_RESUMO_FATURAMENTO V
        LEFT JOIN PCSUPERV S ON (S.CODSUPERVISOR = V.CODSUPERVISOR)
        WHERE V.DTSAIDA >= :desde
        {_FILTRO_VENDA_VALIDA}
        GROUP BY V.CODFILIAL, EXTRACT(YEAR FROM V.DTSAIDA),
                 EXTRACT(MONTH FROM V.DTSAIDA), V.CODUSUR, V.CODSUPERVISOR
        """,
        desde=desde,
    )
    colunas = [d[0] for d in cursor.description]
    return pd.DataFrame(cursor.fetchall(), columns=colunas)


def _consultar_peso(cursor, desde: date) -> pd.DataFrame:
    cursor.execute(
        f"""
        SELECT CODFILIAL, EXTRACT(YEAR FROM DTMOV) ANO,
               EXTRACT(MONTH FROM DTMOV) MES, CODUSUR,
               ROUND(SUM({_PESO_POR_LINHA}), 2) PESOLIQ
        FROM (
            SELECT {_COLUNAS_PESO} FROM FNORTE.GFN_MVIEW_VENDAS_HIST
            WHERE DTMOV >= :desde
            UNION ALL
            SELECT {_COLUNAS_PESO} FROM FNORTE.GFN_MVIEW_VENDAS_ANO_ATUAL
        )
        WHERE DTMOV >= :desde
        GROUP BY CODFILIAL, EXTRACT(YEAR FROM DTMOV),
                 EXTRACT(MONTH FROM DTMOV), CODUSUR
        """,
        desde=desde,
    )
    colunas = [d[0] for d in cursor.description]
    return pd.DataFrame(cursor.fetchall(), columns=colunas)


def juntar_devolucao(
    vendas: pd.DataFrame, cursor, desde: date, colunas: dict[str, str]
) -> pd.DataFrame:
    """
    Soma a devolução (mesma view e mesma data de entrada do faturamento
    mensal) nas vendas e calcula VENDA_LIQ = VENDA_BRUTA − devolução — o
    "faturamento" do WinThor. `colunas`: nome no CSV → coluna da view de
    devolução, além de filial/ano/mês (ex: {"CODPROD": "CODPROD"}). Usada
    pelos arquivos por produto e por cliente.
    """
    selecao = ", ".join(f"{origem} {nome}" for nome, origem in colunas.items())
    agrupamento = ", ".join(colunas.values())
    cursor.execute(
        f"""
        SELECT CODFILIAL, EXTRACT(YEAR FROM DTENT) ANO,
               EXTRACT(MONTH FROM DTENT) MES, {selecao},
               ROUND(SUM(VLDEVOLUCAO), 2) VALOR_DEV
        FROM VIEW_DEVOL_RESUMO_FATURAMENTO
        WHERE DTENT >= :desde
        GROUP BY CODFILIAL, EXTRACT(YEAR FROM DTENT),
                 EXTRACT(MONTH FROM DTENT), {agrupamento}
        """,
        desde=desde,
    )
    devolucao = pd.DataFrame(cursor.fetchall(), columns=[d[0] for d in cursor.description])
    chaves = ["CODFILIAL", "ANO", "MES", *colunas]

    for coluna in chaves:
        vendas[coluna] = vendas[coluna].astype(float)
        devolucao[coluna] = devolucao[coluna].astype(float)

    # Outer: produto/cliente com devolução num mês sem venda também conta.
    dados = vendas.merge(devolucao, on=chaves, how="outer")
    valores = [c for c in dados.columns if c not in chaves]
    dados[valores] = dados[valores].fillna(0)
    dados["VENDA_LIQ"] = (dados["VENDA_BRUTA"] - dados["VALOR_DEV"]).round(2)

    for coluna in ("CODFILIAL", "ANO", "MES"):
        dados[coluna] = dados[coluna].astype(int)

    return dados


def _consultar_devolucao(cursor, desde: date) -> pd.DataFrame:
    cursor.execute(
        """
        SELECT CODFILIAL, EXTRACT(YEAR FROM DTENT) ANO,
               EXTRACT(MONTH FROM DTENT) MES, CODUSUR,
               ROUND(SUM(VLDEVOLUCAO), 2) VALOR_DEV
        FROM VIEW_DEVOL_RESUMO_FATURAMENTO
        WHERE DTENT >= :desde
        GROUP BY CODFILIAL, EXTRACT(YEAR FROM DTENT),
                 EXTRACT(MONTH FROM DTENT), CODUSUR
        """,
        desde=desde,
    )
    colunas = [d[0] for d in cursor.description]
    return pd.DataFrame(cursor.fetchall(), columns=colunas)


def _consultar_meta(cursor, desde: date) -> pd.DataFrame:
    cursor.execute(
        """
        SELECT CODFILIAL, EXTRACT(YEAR FROM DATA) ANO,
               EXTRACT(MONTH FROM DATA) MES, CODUSUR,
               ROUND(SUM(VLVENDAPREV), 2) VALOR_META
        FROM FNORTE.PCMETARCA
        WHERE DATA >= :desde
        GROUP BY CODFILIAL, EXTRACT(YEAR FROM DATA),
                 EXTRACT(MONTH FROM DATA), CODUSUR
        """,
        desde=desde,
    )
    colunas = [d[0] for d in cursor.description]
    return pd.DataFrame(cursor.fetchall(), columns=colunas)


def _consultar_cadastro_rca(cursor) -> pd.DataFrame:
    cursor.execute(
        """
        SELECT U.CODUSUR, U.NOME NOME_RCA, U.CODSUPERVISOR COD_SUPERVISOR_CAD,
               S.NOME NOME_SUPERVISOR_CAD
        FROM PCUSUARI U
        LEFT JOIN PCSUPERV S ON (S.CODSUPERVISOR = U.CODSUPERVISOR)
        """
    )
    colunas = [d[0] for d in cursor.description]
    return pd.DataFrame(cursor.fetchall(), columns=colunas)


def gerar_tabela(
    ano_inicio: int = ANO_INICIO_PADRAO, desde: date | None = None
) -> pd.DataFrame:
    """
    Busca venda, peso, devolução e meta no Oracle (quatro consultas
    simples, cada uma já agregada no banco) e junta em Python por
    filial/ano/mês/vendedor — ver docstring do módulo pras fontes. A
    meta entra mesmo sem venda no mês (mesma soma da rotina 8139).
    """
    desde = desde or date(ano_inicio, 1, 1)
    conexao = get_connection()

    try:
        cursor = conexao.cursor()
        vendas = _consultar_vendas(cursor, desde)
        peso = _consultar_peso(cursor, desde)
        devolucao = _consultar_devolucao(cursor, desde)
        meta = _consultar_meta(cursor, desde)
        cadastro = _consultar_cadastro_rca(cursor)
    finally:
        conexao.close()

    chave = ["CODFILIAL", "ANO", "MES", "CODUSUR"]
    dados = vendas.merge(peso, on=chave, how="left")
    # "outer": devolução de quem NÃO vendeu no mês também desconta — igual
    # à 8280 (ex: Timon mar/2025, RCA 8952 sem venda e R$ 79.500 de
    # devolução). Com "left" ela sumia: R$ 270 mil a mais de faturamento
    # em 2025 (25 devoluções). Conferido com a 8280 em 07/10/2026.
    dados = dados.merge(devolucao, on=chave, how="outer")
    # "outer": a meta de quem NÃO vendeu no mês também entra (ex: a conta
    # "COMERCIAL FERRONORTE LTDA-F09-TIMON", R$ 466 mil em set/2026) — igual
    # à rotina 8139. Com "left" essa meta sumia e a meta da filial ficava
    # menor que a do banco (R$ 67 mi a menos em jan-out/2026).
    meta = meta[meta["VALOR_META"] > 0]
    # Meta de mês que ainda não chegou (nov/dez) fica fora: senão "a meta
    # de 2026" somaria o ano inteiro contra o realizado só até hoje (o
    # atingimento das filiais caía pra 53%-76% em out/2026).
    hoje = date.today()
    meta = meta[(meta["ANO"] * 100 + meta["MES"]) <= hoje.year * 100 + hoje.month]
    dados = dados.merge(meta, on=chave, how="outer")

    # Linha só de meta: sem venda (zero) e com o supervisor do cadastro do
    # RCA (o da venda não existe).
    dados = dados.merge(cadastro, on="CODUSUR", how="left")
    for coluna in ("VENDA_BRUTA", "VENDA_TABELA", "QT_NOTAS"):
        dados[coluna] = dados[coluna].fillna(0)
    dados["QT_NOTAS"] = dados["QT_NOTAS"].astype(int)
    dados["CODSUPERVISOR"] = dados["CODSUPERVISOR"].fillna(dados["COD_SUPERVISOR_CAD"])
    dados["NOME_SUPERVISOR"] = dados["NOME_SUPERVISOR"].fillna(dados["NOME_SUPERVISOR_CAD"])
    dados["CONTA_EMPRESA"] = (
        dados["NOME_RCA"].fillna("").str.upper().str.contains(_NOME_CONTA_EMPRESA)
    )

    dados["CODFILIAL"] = dados["CODFILIAL"].astype(int)
    dados["ANO"] = dados["ANO"].astype(int)
    dados["MES"] = dados["MES"].astype(int)
    dados["PESOLIQ"] = dados["PESOLIQ"].fillna(0.0)
    dados["VALOR_DEV"] = dados["VALOR_DEV"].fillna(0.0)
    dados["VALOR_META"] = dados["VALOR_META"].fillna(0.0)
    dados["VALORDESC"] = dados["VALORDESC"].fillna(0.0)
    dados["VENDA_LIQ"] = (dados["VENDA_BRUTA"] - dados["VALOR_DEV"]).round(2)

    dados = dados.rename(
        columns={"CODUSUR": "COD_RCA", "CODSUPERVISOR": "COD_SUPERVISOR"}
    )

    return dados[COLUNAS_SAIDA]


def atualizar(completa: bool) -> None:
    """
    Completa: tudo desde 2020. Parcial: busca no Oracle só o mês atual e
    o anterior e junta com os meses mais antigos do CSV que já existe.
    """
    if completa or not ARQUIVO_FATURAMENTO_MENSAL.exists():
        gravar_csv(gerar_tabela(), ARQUIVO_FATURAMENTO_MENSAL)
        return

    desde = inicio_da_janela_parcial()
    antigo = antes_da_janela_mensal(ler_csv(ARQUIVO_FATURAMENTO_MENSAL), desde)
    gravar_csv(
        pd.concat([antigo, gerar_tabela(desde=desde)], ignore_index=True),
        ARQUIVO_FATURAMENTO_MENSAL,
    )


def carregar_faturamento_mensal() -> pd.DataFrame:
    garantir([ARQUIVO_FATURAMENTO_MENSAL], atualizar, "faturamento mensal")
    dados = ler_csv(ARQUIVO_FATURAMENTO_MENSAL)
    #removendo as colunas vazias criadas durante a execução
    dados = dados.loc [
        :,
        ~dados.columns.str.startswith("Unnamed")
    ]
    return padronizar_filiais(dados, dados["CODFILIAL"])
