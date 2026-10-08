"""
Carregamento dos dados de NPS (respostas de avaliação, Azure SQL).

Traz as respostas individuais (filial, data, nota) pro pandas, uma
linha por resposta, já com as colunas de classificação (promotor/
neutro/detrator) — o motor genérico (orquestrador.py) soma e agrupa
em cima disso, como faz com qualquer outro indicador.
"""
import time

import pandas as pd

from core.repositories.azure import get_connection
from core.repositories.filiais_repository import padronizar_filiais

# Os dados são "ao vivo" (respostas entram todo dia) e a carga completa
# leva ~1,5s, então uma consulta que compara períodos (que carrega duas
# vezes) reaproveita a mesma leitura por alguns minutos.
_SEGUNDOS_DE_CACHE = 300
_cache: dict = {"quando": 0.0, "dados": None}


def carregar_avaliacoes_nps() -> pd.DataFrame:
    """
    Uma linha por resposta válida (nota de 0 a 10): FILIAL, DATA (só a
    data, sem hora), MES, ANO, NOTA e as colunas RESPOSTA/PROMOTOR/
    NEUTRO/DETRATOR (1 ou 0) — promotor é nota 9-10, neutro 7-8,
    detrator 0-6.
    """
    agora = time.monotonic()

    if (
        _cache["dados"] is not None
        and agora - _cache["quando"] < _SEGUNDOS_DE_CACHE
    ):
        return _cache["dados"]

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT F.IdFilialFerronorte, A.DataHora, A.Nota
            FROM dbo.Avaliacoes AS A
            INNER JOIN dbo.Filiais AS F
                ON A.FilialId = F.Id
            """
        )
        registros = [tuple(registro) for registro in cursor.fetchall()]
    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()

    dados = pd.DataFrame(registros, columns=["CODFILIAL", "DATAHORA", "NOTA"])
    dados["NOTA"] = pd.to_numeric(dados["NOTA"], errors="coerce")
    dados = dados[dados["NOTA"].between(0, 10)].copy()

    dados = padronizar_filiais(dados, dados["CODFILIAL"])
    dados["DATA"] = pd.to_datetime(dados["DATAHORA"]).dt.normalize()
    dados["MES"] = dados["DATA"].dt.month
    dados["ANO"] = dados["DATA"].dt.year
    dados["RESPOSTA"] = 1
    dados["PROMOTOR"] = (dados["NOTA"] >= 9).astype(int)
    dados["NEUTRO"] = dados["NOTA"].between(7, 8).astype(int)
    dados["DETRATOR"] = (dados["NOTA"] <= 6).astype(int)

    dados = dados.drop(columns=["DATAHORA"])

    _cache["dados"] = dados
    _cache["quando"] = agora

    return dados
