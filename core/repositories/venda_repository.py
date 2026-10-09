"""
Desconto por VENDA (nota fiscal = pedido, 1 pra 1 no WinThor).

Um CSV, gerado do Oracle e atualizado em segundo plano por
`core/services/atualizador_service.py` (mesma regra dos outros):
`desconto_venda.csv` — uma linha por nota, desde 2025 (decisão da usuária
em 09/10/2026: ~700 mil notas por ano; desde 2020 seriam 4,3 milhões).
Os totais por filial/RCA/cliente/produto desde 2020 continuam nos outros
arquivos.

Mesma conta de desconto da rotina 8302 (VLDESCONTO x QT) e mesmos filtros
de venda válida do faturamento mensal. A nota não traz devolução: o
número que importa aqui é o desconto dado NA venda.

A "venda" é identificada pela transação (NUMTRANSVENDA, única); o número
da nota se repete entre filiais (cada uma tem a sua numeração) — por isso
"a nota 123456" pode achar mais de uma venda.
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
from core.repositories.faturamento_diario_repository import construir_mapa_rca_nome
from core.repositories.faturamento_repository import RAIZ_PROJETO, _FILTRO_VENDA_VALIDA
from core.repositories.filiais_repository import padronizar_filiais
from core.logger import obter_logger

logger = obter_logger(__name__)

ARQUIVO_DESCONTO_VENDA = RAIZ_PROJETO / "data" / "desconto_venda.csv"
ANO_INICIO_VENDA = 2025

COLUNAS = [
    "CODFILIAL", "DATA", "ANO", "MES", "NUMTRANSVENDA", "NUMNOTA", "NUMPED",
    "CODCLI", "COD_RCA", "COD_SUPERVISOR", "QT_ITENS",
    "VALORDESC", "VENDA_TABELA", "VENDA_BRUTA",
]


def _buscar(desde: date) -> pd.DataFrame:
    from core.repositories.oracle import get_connection

    conexao = get_connection()

    try:
        cursor = conexao.cursor()
        cursor.arraysize = 10000
        cursor.execute(
            f"""
            SELECT V.CODFILIAL, TRUNC(V.DTSAIDA) DATA, V.NUMTRANSVENDA,
                   MAX(V.NUMNOTA) NUMNOTA, MAX(V.NUMPED) NUMPED,
                   MAX(V.CODCLI) CODCLI, MAX(V.CODUSUR) COD_RCA,
                   MAX(V.CODSUPERVISOR) COD_SUPERVISOR, COUNT(*) QT_ITENS,
                   ROUND(SUM(V.VLDESCONTO * V.QT), 4) VALORDESC,
                   ROUND(SUM(V.VLTABELA), 2) VENDA_TABELA,
                   ROUND(SUM(V.VLVENDA), 2) VENDA_BRUTA
            FROM VIEW_VENDAS_RESUMO_FATURAMENTO V
            WHERE V.DTSAIDA >= :desde
            {_FILTRO_VENDA_VALIDA}
            GROUP BY V.CODFILIAL, TRUNC(V.DTSAIDA), V.NUMTRANSVENDA
            """,
            desde=desde,
        )
        dados = pd.DataFrame(cursor.fetchall(), columns=[d[0] for d in cursor.description])
    finally:
        conexao.close()

    dados["DATA"] = pd.to_datetime(dados["DATA"])
    dados["ANO"] = dados["DATA"].dt.year
    dados["MES"] = dados["DATA"].dt.month

    for coluna in ("CODFILIAL", "NUMTRANSVENDA", "NUMNOTA", "NUMPED", "CODCLI", "COD_RCA"):
        dados[coluna] = dados[coluna].astype("int64")

    return dados[COLUNAS]


def atualizar(completa: bool) -> None:
    """Completa: tudo desde 2025. Parcial: só o mês atual e o anterior,
    juntando com os meses mais antigos do CSV."""
    if completa or not ARQUIVO_DESCONTO_VENDA.exists():
        dados = _buscar(date(ANO_INICIO_VENDA, 1, 1))
    else:
        desde = inicio_da_janela_parcial()
        antigo = antes_da_janela_mensal(ler_csv(ARQUIVO_DESCONTO_VENDA), desde)
        # A data lida do CSV é texto e a do Oracle é data: sem converter,
        # o arquivo saía com dois formatos ("2025-01-02" e "2026-10-08
        # 00:00:00") e não abria mais.
        antigo["DATA"] = pd.to_datetime(antigo["DATA"], format="ISO8601")
        dados = pd.concat([antigo, _buscar(desde)], ignore_index=True)

    gravar_csv(dados, ARQUIVO_DESCONTO_VENDA)


def _garantir() -> None:
    garantir([ARQUIVO_DESCONTO_VENDA], atualizar, "desconto por venda")


# Ler e juntar 1,2 milhão de linhas leva ~8 s: fica em memória até o
# arquivo mudar (o atualizador regrava de hora em hora).
_cache: dict = {"versao": None, "dados": None}


def carregar_desconto_venda() -> pd.DataFrame:
    """Desconto por nota, com o cliente (nome, empresa) e o nome do RCA."""
    _garantir()
    versao = ARQUIVO_DESCONTO_VENDA.stat().st_mtime

    if _cache["versao"] != versao:
        _cache["dados"] = _montar_dados()
        _cache["versao"] = versao

    return _cache["dados"]


def _montar_dados() -> pd.DataFrame:
    dados = ler_csv(ARQUIVO_DESCONTO_VENDA)
    dados["DATA"] = pd.to_datetime(dados["DATA"], format="ISO8601")
    dados["DATA_TEXTO"] = dados["DATA"].dt.strftime("%d/%m/%Y")
    dados = dados.merge(
        carregar_clientes()[["CODCLI", "CLIENTE", "CNPJ", "CIDADE", "EMPRESA", "NOME_EMPRESA", "CNPJ_EMPRESA"]],
        on="CODCLI", how="left",
    )
    dados["NOME_RCA"] = dados["COD_RCA"].map(construir_mapa_rca_nome())
    return padronizar_filiais(dados, dados["CODFILIAL"])


# O arquivo de venda também tem cliente/empresa/RCA/supervisor: numa
# pergunta "vendas com mais desconto do Mateus" ele responde sozinho, em
# vez de dar o erro de "arquivos diferentes" (ver buscar_dados_brutos).
carregar_desconto_venda.tambem_tem = ("cliente", "empresa", "rca", "supervisor")


def resolver_vendas(numero, filiais=None) -> list[int]:
    """
    Número da nota OU do pedido → a(s) venda(s) (transação). A numeração
    da nota se repete entre filiais: com filial na pergunta, só a dela;
    sem, todas as que tiverem esse número.
    """
    texto = str(numero).strip()

    if not texto.isdigit():
        raise ValueError(
            f"'{texto}' não é um número de nota ou pedido. Pergunte o número "
            "ao usuário."
        )

    dados = carregar_desconto_venda()
    achadas = dados[(dados["NUMNOTA"] == int(texto)) | (dados["NUMPED"] == int(texto))]

    if filiais:
        achadas = achadas[achadas["FILIAL"].isin(filiais)]

    if achadas.empty:
        raise ValueError(
            f"Não encontrei a nota ou pedido {texto} desde {ANO_INICIO_VENDA} "
            "(o detalhe por venda só vai até 2025)."
        )

    # O mesmo número em filiais diferentes são vendas diferentes: nunca
    # soma — pergunta qual (como nos clientes com o mesmo nome).
    if achadas["FILIAL"].nunique() > 1:
        opcoes = "; ".join(
            f"{numero}. filial {linha.FILIAL}, {linha.DATA_TEXTO}, cliente "
            f"{linha.CLIENTE}, desconto de R$ {linha.VALORDESC:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            for numero, linha in enumerate(achadas.itertuples(), start=1)
        )
        raise ValueError(
            f"O número {texto} aparece em vendas de filiais diferentes: {opcoes}. "
            "Mostre as opções ao usuário e pergunte de qual filial é; depois "
            "consulte de novo com a filial no filtro."
        )

    return achadas["NUMTRANSVENDA"].drop_duplicates().tolist()
