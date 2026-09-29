"""

Só leitura no banco (nenhum INSERT/UPDATE/DELETE). Pensado para rodar
periodicamente (frequência e agendamento a definir)

Fonte dos dados, achadas e validadas por comparação com o CSV
manual:
- Venda (bruta e de tabela), notas: `VIEW_VENDAS_RESUMO_FATURAMENTO` —
  bate exato (0,00 de diferença) com o CSV. NÃO usar `PCMOV`
  direto, ela duplica ~25-29% das vendas (ver docs).
- Devolução: `VIEW_DEVOL_RESUMO_FATURAMENTO` — também bate exato nos 6
  anos (essa view já resolve sozinha a duplicação que a
  `GFN_MVIEW_DEV_HIST` tinha, sem precisar aceitar nenhuma margem).
- Peso: continua vindo de `GFN_MVIEW_VENDAS_HIST`/`GFN_MVIEW_VENDAS_ANO_ATUAL`,
  com a correção do bug de KG (ver `_PESO_POR_LINHA` abaixo) — as views de
  venda/devolução acima não têm a coluna `UNIDADE`, então não dá pra
  aplicar a mesma correção nelas.
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
ARQUIVO_PADRAO = RAIZ_PROJETO / "dados" / "faturamento_mensal.csv"

# Colunas que src/*.py de fato lê desse arquivo (catalogo.py e
# metas_data.py) — nada além disso precisa ser gerado.
COLUNAS_SAIDA = [
    "CODFILIAL", "ANO", "MES", "COD_RCA", "COD_SUPERVISOR",
    "NOME_SUPERVISOR", "VENDA_BRUTA", "VALORDESC", "VENDA_LIQ",
    "PESOLIQ", "QT_NOTAS", "VALOR_META",
]

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


def _consultar_vendas(cursor, desde: date) -> pd.DataFrame:
    cursor.execute(
        f"""
        SELECT V.CODFILIAL, EXTRACT(YEAR FROM V.DTSAIDA) ANO,
               EXTRACT(MONTH FROM V.DTSAIDA) MES, V.CODUSUR,
               V.CODSUPERVISOR, MAX(S.NOME) NOME_SUPERVISOR,
               COUNT(DISTINCT V.NUMTRANSVENDA) QT_NOTAS,
               ROUND(SUM(V.VLVENDA), 2) VENDA_BRUTA,
               ROUND(SUM(V.VLTABELA), 2) VENDA_TABELA
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


def gerar_tabela(ano_inicio: int) -> pd.DataFrame:
    """
    Busca venda, peso, devolução e meta no Oracle (quatro consultas
    simples, cada uma já agregada no banco) e junta em Python por
    filial/ano/mês/vendedor — ver docstring do módulo pras fontes.
    """
    desde = date(ano_inicio, 1, 1)
    conexao = get_connection()

    try:
        cursor = conexao.cursor()
        vendas = _consultar_vendas(cursor, desde)
        peso = _consultar_peso(cursor, desde)
        devolucao = _consultar_devolucao(cursor, desde)
        meta = _consultar_meta(cursor, desde)
    finally:
        conexao.close()

    chave = ["CODFILIAL", "ANO", "MES", "CODUSUR"]
    dados = vendas.merge(peso, on=chave, how="left")
    dados = dados.merge(devolucao, on=chave, how="left")
    dados = dados.merge(meta, on=chave, how="left")

    dados["CODFILIAL"] = dados["CODFILIAL"].astype(int)
    dados["ANO"] = dados["ANO"].astype(int)
    dados["MES"] = dados["MES"].astype(int)
    dados["PESOLIQ"] = dados["PESOLIQ"].fillna(0.0)
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
