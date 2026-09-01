import pandas as pd

from src import meta_tonelada_queries as mtq


def _dados_teste():
    return pd.DataFrame(
        [
            {
                "FILIAL": "COMERCIAL FERRONORTE LTDA-F09-TIMON",
                "ANO": 2025,
                "MES": 1,
                "RCA": "AURORA ANDRADE-F09",
                "Meta Tonelada - Filial": 500.0,
                "Meta Tonelada - RCA": 300.0,
            },
            {
                "FILIAL": "COMERCIAL FERRONORTE LTDA-F09-TIMON",
                "ANO": 2025,
                "MES": 1,
                "RCA": "JUNIOR PEREIRA-F09",
                "Meta Tonelada - Filial": 500.0,
                "Meta Tonelada - RCA": 200.0,
            },
            {
                "FILIAL": "COMERCIAL FERRONORTE LTDA-F01-MATRIZ",
                "ANO": 2025,
                "MES": 1,
                "RCA": "ALGUEM-F01",
                "Meta Tonelada - Filial": 100.0,
                "Meta Tonelada - RCA": 100.0,
            },
        ]
    )


def test_consultar_meta_tonelada_sem_dado_retorna_nao_encontrado(
    monkeypatch,
):
    monkeypatch.setattr(
        mtq, "carregar_meta_tonelada", lambda: _dados_teste()
    )

    resultado = mtq.consultar_meta_tonelada(anos=[2019])

    assert resultado["encontrado"] is False


def test_consultar_meta_tonelada_filial_nao_duplica_por_rca(monkeypatch):
    monkeypatch.setattr(
        mtq, "carregar_meta_tonelada", lambda: _dados_teste()
    )

    resultado = mtq.consultar_meta_tonelada(
        filiais=["COMERCIAL FERRONORTE LTDA-F09-TIMON"],
        anos=[2025],
    )

    assert resultado["encontrado"] is True
    # a meta da filial é 500 (não 1000 - não pode dobrar por ter 2 RCAs)
    assert resultado["meta_tonelada_filial"] == 500.0
    # a meta de RCA soma normalmente entre os 2 vendedores
    assert resultado["meta_tonelada_rca"] == 500.0


def test_consultar_meta_tonelada_rca_especifico(monkeypatch):
    monkeypatch.setattr(
        mtq, "carregar_meta_tonelada", lambda: _dados_teste()
    )

    resultado = mtq.consultar_meta_tonelada(
        rcas=["AURORA ANDRADE-F09"],
        anos=[2025],
    )

    assert resultado["meta_tonelada_rca"] == 300.0
    assert resultado["meta_tonelada_filial"] == 500.0


def test_consultar_meta_tonelada_agrupado_por_filial(monkeypatch):
    monkeypatch.setattr(
        mtq, "carregar_meta_tonelada", lambda: _dados_teste()
    )

    resultado = mtq.consultar_meta_tonelada(
        anos=[2025],
        agrupar_por=["filial"],
    )

    assert resultado["encontrado"] is True
    valores = {
        item["filial"]: item["meta_tonelada_filial"]
        for item in resultado["resultados"]
    }
    assert valores["COMERCIAL FERRONORTE LTDA-F09-TIMON"] == 500.0
    assert valores["COMERCIAL FERRONORTE LTDA-F01-MATRIZ"] == 100.0
