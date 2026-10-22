"""
Mix de produtos: o que cada cliente comprou, produto a produto.

Um CSV, gerado do Oracle e atualizado em segundo plano por
`core/services/atualizador_service.py`: `cliente_produto.csv` — venda
bruta, desconto, faturamento de tabela e devolução por
filial/ano/mês/cliente/produto, desde 2025 (desde 2020 seriam ~7 milhões
de linhas), sem RCA. Mesma view, filtros e conta do faturamento mensal
(como a rotina 8306 analítica).

É o arquivo das consultas que juntam cliente/empresa com
produto/família/grupo ("quais produtos o Mateus comprou", "quem comprou
vergalhão 10") — ver `orquestrador.buscar_dados_brutos`.
"""
from datetime import date

import pandas as pd

from core.repositories.arquivos_repository import (
    antes_da_janela_mensal,
    garantir,
    gravar_csv,
    inicio_da_janela_parcial,
    ler_csv,
)
from core.repositories.cliente_repository import carregar_clientes
from core.repositories.faturamento_repository import RAIZ_PROJETO, _FILTRO_VENDA_VALIDA, juntar_devolucao
from core.repositories.filiais_repository import padronizar_filiais
from core.repositories.produto_repository import SEM_GRUPO, carregar_produtos

ARQUIVO_CLIENTE_PRODUTO = RAIZ_PROJETO / "data" / "cliente_produto.csv"
ANO_INICIO_MIX = 2025

COLUNAS = [
    "CODFILIAL", "ANO", "MES", "CODCLI", "CODPROD",
    "VALORDESC", "VENDA_TABELA", "VENDA_BRUTA", "VALOR_DEV", "VENDA_LIQ",
]


def _buscar(desde: date) -> pd.DataFrame:
    from core.repositories.oracle import get_connection

    conexao = get_connection()

    try:
        cursor = conexao.cursor()
        cursor.arraysize = 20000
        cursor.execute(
            f"""
            SELECT V.CODFILIAL, EXTRACT(YEAR FROM V.DTSAIDA) ANO,
                   EXTRACT(MONTH FROM V.DTSAIDA) MES, V.CODCLI, V.CODPROD,
                   ROUND(SUM(V.VLTABELA) - SUM(V.VLVENDA), 2) VALORDESC,
                   ROUND(SUM(V.VLTABELA), 2) VENDA_TABELA,
                   ROUND(SUM(V.VLVENDA), 2) VENDA_BRUTA
            FROM VIEW_VENDAS_RESUMO_FATURAMENTO V
            WHERE V.DTSAIDA >= :desde
            {_FILTRO_VENDA_VALIDA}
            GROUP BY V.CODFILIAL, EXTRACT(YEAR FROM V.DTSAIDA),
                     EXTRACT(MONTH FROM V.DTSAIDA), V.CODCLI, V.CODPROD
            """,
            desde=desde,
        )
        vendas = pd.DataFrame(cursor.fetchall(), columns=[d[0] for d in cursor.description])
        dados = juntar_devolucao(vendas, cursor, desde, {"CODCLI": "CODCLI", "CODPROD": "CODPROD"})
    finally:
        conexao.close()

    for coluna in ("CODCLI", "CODPROD"):
        dados[coluna] = dados[coluna].astype("int64")

    return dados[COLUNAS]


def atualizar(completa: bool) -> None:
    """Completa: tudo desde 2025. Parcial: só o mês atual e o anterior,
    juntando com os meses mais antigos do CSV."""
    if completa or not ARQUIVO_CLIENTE_PRODUTO.exists():
        dados = _buscar(date(ANO_INICIO_MIX, 1, 1))
    else:
        desde = inicio_da_janela_parcial()
        antigo = antes_da_janela_mensal(ler_csv(ARQUIVO_CLIENTE_PRODUTO), desde)
        dados = pd.concat([antigo, _buscar(desde)], ignore_index=True)

    gravar_csv(dados, ARQUIVO_CLIENTE_PRODUTO)


def _garantir() -> None:
    garantir([ARQUIVO_CLIENTE_PRODUTO], atualizar, "mix de produtos dos clientes")


# Juntar o cadastro (cliente e produto) em ~2 milhões de linhas leva alguns
# segundos: fica em memória até o arquivo mudar.
_cache: dict = {"versao": None, "dados": None}


def _montar() -> pd.DataFrame:
    dados = ler_csv(ARQUIVO_CLIENTE_PRODUTO)
    # Texto como categoria: o nome do cliente/produto se repete em muitas
    # linhas.
    clientes = carregar_clientes()[
        ["CODCLI", "CLIENTE", "CNPJ", "CIDADE", "EMPRESA", "NOME_EMPRESA", "CNPJ_EMPRESA"]
    ]
    produtos = carregar_produtos()
    dados = dados.merge(
        clientes.astype({coluna: "category" for coluna in clientes.columns if coluna != "CODCLI"}),
        on="CODCLI", how="left",
    ).merge(
        produtos.astype({coluna: "category" for coluna in produtos.columns if coluna != "CODPROD"}),
        on="CODPROD", how="left",
    )
    # Produto fora do cadastro: "SEM GRUPO", como no arquivo por produto.
    dados["GRUPO"] = dados["GRUPO"].astype(object).fillna(SEM_GRUPO).astype("category")
    dados = padronizar_filiais(dados, dados["CODFILIAL"])
    return dados.astype({"FILIAL": "category", "ESTADO": "category"})


def carregar_cliente_produto(filtros: dict | None = None) -> pd.DataFrame:
    """Venda por filial/mês/cliente/produto, com o cadastro dos dois."""
    anos = [int(ano) for ano in (filtros or {}).get("ano") or []]

    if anos and max(anos) < ANO_INICIO_MIX:
        raise ValueError(
            f"Os produtos comprados por cliente começam em {ANO_INICIO_MIX}: "
            f"consulte de {ANO_INICIO_MIX} em diante."
        )

    _garantir()
    versao = ARQUIVO_CLIENTE_PRODUTO.stat().st_mtime

    if _cache["versao"] != versao:
        _cache.update(versao=versao, dados=_montar())

    return _cache["dados"]


# O motor passa os filtros (pra avisar do período) e usa este arquivo
# quando a consulta junta cliente/empresa com produto/família/grupo.
carregar_cliente_produto.recebe_filtros = True
carregar_cliente_produto.tambem_tem = ("cliente", "empresa", "produto", "familia", "grupo")
