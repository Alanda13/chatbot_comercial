"""
Consulta o Oracle de produção (WinThor) e regrava o CSV de faturamento
diário que `src.faturamento_diario_data.carregar_faturamento_8302` lê —
no lugar da exportação manual da rotina 8302.

Só leitura no banco (nenhum INSERT/UPDATE/DELETE).

Fontes (ver docs/arquitetura_atual.md):
- Venda (bruta, de tabela, desconto, nº de notas), nome do RCA:
  `GFN_MVIEW_VENDAS_ATUAL` — achada a partir de um relatório do diário
  que o Ayllan (colega) já usa. Cobre o histórico inteiro (2009 até
  hoje) numa view só, sem precisar dos filtros de negócio (tipo de
  nota, código fiscal, condição de venda) que o mensal precisa — já
  validado batendo exato, campo a campo, num caso que a
  `VIEW_VENDAS_RESUMO_FATURAMENTO` (usada no mensal) errava feio
  especificamente no desconto (ela calcula por diferença tabela−bruta,
  que não bate no diário; aqui o desconto vem de uma coluna própria,
  `VLDESCONTO`, que bate certo).
- Devolução: `VIEW_DEVOL_RESUMO_FATURAMENTO` — mesma fonte já validada
  no mensal, também bate exato no diário.

NÃO inclui forma de pagamento (`COBRANCA`) — esse dado é mais complexo
(a devolução parece ser alocada por forma de pagamento de um jeito
ainda não entendido) e fica pendente, tratado à parte. O arquivo
`carregar_faturamento_8302_cobranca` continua manual por enquanto.

Uso:
    python scripts/atualizar_faturamento_diario_oracle.py
    python scripts/atualizar_faturamento_diario_oracle.py --desde 2024-01-01 --saida dados/teste.csv
"""
import argparse
from datetime import date
from pathlib import Path

import pandas as pd

from src.connection import get_connection

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
ARQUIVO_PADRAO = RAIZ_PROJETO / "dados" / "faturamento_diario.csv"

# Colunas que src/faturamento_diario_data.py e src/catalogo.py de fato
# leem desse arquivo — nada além disso precisa ser gerado.
COLUNAS_SAIDA = [
    "CODFILIAL", "DATA", "COD_RCA", "NOME_RCA",
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


def gerar_tabela(desde: date) -> pd.DataFrame:
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--desde", type=str, default="2020-01-01",
        help="Primeira data a buscar, formato AAAA-MM-DD (padrão: 2020-01-01).",
    )
    parser.add_argument(
        "--saida", type=Path, default=ARQUIVO_PADRAO,
        help="Arquivo CSV a gravar (padrão: sobrescreve o CSV atual).",
    )
    argumentos = parser.parse_args()

    ano, mes, dia = (int(parte) for parte in argumentos.desde.split("-"))
    tabela = gerar_tabela(date(ano, mes, dia))

    argumentos.saida.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_csv(
        argumentos.saida, sep=";", encoding="latin1", decimal=",", index=False,
    )
    print(f"{len(tabela)} linhas gravadas em {argumentos.saida}")


if __name__ == "__main__":
    main()
