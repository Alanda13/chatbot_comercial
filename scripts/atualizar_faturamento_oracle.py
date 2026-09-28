"""
Consulta o Oracle de produção (WinThor) e regrava o CSV de faturamento
mensal que `src.faturamento_data.carregar_faturamento_8280` lê — no lugar
da exportação manual da rotina 8280.

Só leitura no banco (nenhum INSERT/UPDATE/DELETE). Pensado para rodar
periodicamente (frequência e agendamento a definir — ver
docs/arquitetura_atual.md).

Fonte dos dados, todas achadas e validadas por comparação com o CSV
manual (seis anos, todas as filiais e vendedores — ver
docs/arquitetura_atual.md, seção "Investigação: ligar o faturamento no
Oracle"):
- Venda (bruta e de tabela), peso, notas: `GFN_MVIEW_VENDAS_HIST` (até
  31/12/2025) + `GFN_MVIEW_VENDAS_ANO_ATUAL` (ano corrente) — NÃO usar
  `PCMOV` direto, ela duplica ~25-29% das vendas (ver docs).
- Devolução: `GFN_MVIEW_DEV_HIST` + `GFN_MVIEW_DEV_ANO_ATUAL`.
- Meta: `PCMETARCA` (`VLVENDAPREV`, uma linha por vendedor por dia).

Uso:
    python scripts/atualizar_faturamento_oracle.py
    python scripts/atualizar_faturamento_oracle.py --ano-inicio 2022 --saida dados/teste.csv
"""
import argparse
from datetime import date
from pathlib import Path

import pandas as pd

from src.connection import get_connection

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
ARQUIVO_PADRAO = RAIZ_PROJETO / "dados" / "faturamento_8280_2020_2025.csv"

# Colunas que src/*.py de fato lê desse arquivo (catalogo.py e
# metas_data.py) — nada além disso precisa ser gerado.
COLUNAS_SAIDA = [
    "CODFILIAL", "ANO", "MES", "COD_RCA", "COD_SUPERVISOR",
    "NOME_SUPERVISOR", "VENDA_BRUTA", "VALORDESC", "VENDA_LIQ",
    "PESOLIQ", "QT_NOTAS", "VALOR_META",
]


# As duas views (HIST e ANO_ATUAL) têm as mesmas colunas, mas um
# "SELECT *" num UNION ALL junta por POSIÇÃO, não por nome — se a
# ordem das colunas divergir entre as duas views (mesmo com nomes
# iguais), os valores vão parar em colunas erradas em silêncio. Por
# isso cada lado do UNION ALL nomeia as colunas explicitamente.
_COLUNAS_VENDA = (
    "DTMOV, CODFILIAL, CODUSUR, CODSUPERVISOR, SUPERV, NUMTRANSVENDA, "
    "VLVENDA, VLTABELA, TOTPESOLIQ, UNIDADE, QTVENDA"
)

# Peso: pra produto vendido por peça (UNIDADE != 'KG'), TOTPESOLIQ já é
# quantidade × peso cadastrado do produto — correto. Pra produto vendido
# direto em quilos (UNIDADE = 'KG', ex: chapas de aço), a quantidade JÁ é
# o peso — nesse caso TOTPESOLIQ está multiplicando o peso por ele mesmo
# (bug confirmado no próprio WinThor, não só nessa view: o cabeçalho da
# nota, PCNFSAID.TOTPESOLIQ, tem o mesmo erro). Reduziu a margem de erro
# de 3,17% pra 1,18% no ano de 2025 (ver docs/arquitetura_atual.md).
_PESO_POR_LINHA = "CASE WHEN UNIDADE = 'KG' THEN QTVENDA ELSE TOTPESOLIQ END"
_COLUNAS_DEV = "DTENT, CODFILIAL, CODUSUR, VLDEVOLUCAO"


def _consultar_vendas(cursor, desde: date) -> pd.DataFrame:
    cursor.execute(
        f"""
        SELECT CODFILIAL, EXTRACT(YEAR FROM DTMOV) ANO,
               EXTRACT(MONTH FROM DTMOV) MES, CODUSUR, CODSUPERVISOR,
               MAX(SUPERV) NOME_SUPERVISOR,
               COUNT(DISTINCT NUMTRANSVENDA) QT_NOTAS,
               ROUND(SUM(VLVENDA), 2) VENDA_BRUTA,
               ROUND(SUM(VLTABELA), 2) VENDA_TABELA,
               ROUND(SUM({_PESO_POR_LINHA}), 2) PESOLIQ
        FROM (
            SELECT {_COLUNAS_VENDA} FROM FNORTE.GFN_MVIEW_VENDAS_HIST
            WHERE DTMOV >= :desde
            UNION ALL
            SELECT {_COLUNAS_VENDA} FROM FNORTE.GFN_MVIEW_VENDAS_ANO_ATUAL
        )
        WHERE DTMOV >= :desde
        GROUP BY CODFILIAL, EXTRACT(YEAR FROM DTMOV),
                 EXTRACT(MONTH FROM DTMOV), CODUSUR, CODSUPERVISOR
        """,
        desde=desde,
    )
    colunas = [d[0] for d in cursor.description]
    return pd.DataFrame(cursor.fetchall(), columns=colunas)


def _consultar_devolucao(cursor, desde: date) -> pd.DataFrame:
    cursor.execute(
        f"""
        SELECT CODFILIAL, EXTRACT(YEAR FROM DTENT) ANO,
               EXTRACT(MONTH FROM DTENT) MES, CODUSUR,
               ROUND(SUM(VLDEVOLUCAO), 2) VALOR_DEV
        FROM (
            SELECT {_COLUNAS_DEV} FROM FNORTE.GFN_MVIEW_DEV_HIST
            WHERE DTENT >= :desde
            UNION ALL
            SELECT {_COLUNAS_DEV} FROM FNORTE.GFN_MVIEW_DEV_ANO_ATUAL
        )
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


def gerar_tabela(ano_inicio: int) -> pd.DataFrame:
    """
    Busca venda, devolução e meta no Oracle (três consultas simples,
    cada uma já agregada no banco) e junta em Python por
    filial/ano/mês/vendedor — ver docstring do módulo pras fontes.
    """
    desde = date(ano_inicio, 1, 1)
    conexao = get_connection()

    try:
        cursor = conexao.cursor()
        vendas = _consultar_vendas(cursor, desde)
        devolucao = _consultar_devolucao(cursor, desde)
        meta = _consultar_meta(cursor, desde)
    finally:
        conexao.close()

    chave = ["CODFILIAL", "ANO", "MES", "CODUSUR"]
    dados = vendas.merge(devolucao, on=chave, how="left")
    dados = dados.merge(meta, on=chave, how="left")

    dados["CODFILIAL"] = dados["CODFILIAL"].astype(int)
    dados["ANO"] = dados["ANO"].astype(int)
    dados["MES"] = dados["MES"].astype(int)
    dados["VALOR_DEV"] = dados["VALOR_DEV"].fillna(0.0)
    dados["VALOR_META"] = dados["VALOR_META"].fillna(0.0)
    dados["VALORDESC"] = (dados["VENDA_BRUTA"] - dados["VENDA_TABELA"]).round(2)
    dados["VENDA_LIQ"] = (dados["VENDA_BRUTA"] - dados["VALOR_DEV"]).round(2)

    dados = dados.rename(
        columns={"CODUSUR": "COD_RCA", "CODSUPERVISOR": "COD_SUPERVISOR"}
    )

    return dados[COLUNAS_SAIDA]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ano-inicio", type=int, default=2020,
        help="Primeiro ano a buscar (padrão: 2020, igual ao CSV atual).",
    )
    parser.add_argument(
        "--saida", type=Path, default=ARQUIVO_PADRAO,
        help="Arquivo CSV a gravar (padrão: sobrescreve o CSV atual).",
    )
    argumentos = parser.parse_args()

    tabela = gerar_tabela(argumentos.ano_inicio)

    argumentos.saida.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_csv(
        argumentos.saida, sep=";", encoding="latin1", decimal=",", index=False,
    )
    print(f"{len(tabela)} linhas gravadas em {argumentos.saida}")


if __name__ == "__main__":
    main()
