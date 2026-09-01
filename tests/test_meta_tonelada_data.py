import pandas as pd
import pytest

from src import meta_tonelada_data as mtd


def _dados_teste():
    return pd.DataFrame(
        [
            {
                "FILIAL": "COMERCIAL FERRONORTE LTDA-F09-TIMON",
                "ANO": 2025,
                "MES": 1,
                "RCA": "AURORA ANDRADE-F01",
                "Meta Tonelada - Filial": 622.03,
                "Meta Tonelada - RCA": 175.03,
            },
            {
                "FILIAL": "COMERCIAL FERRONORTE LTDA-F01-MATRIZ",
                "ANO": 2025,
                "MES": 1,
                "RCA": "JUNIOR PEREIRA-F01",
                "Meta Tonelada - Filial": 400.00,
                "Meta Tonelada - RCA": 100.00,
            },
        ]
    )


def test_resolver_nome_filial_tonelada_encontra_por_substring(monkeypatch):
    monkeypatch.setattr(
        mtd, "carregar_meta_tonelada", lambda: _dados_teste()
    )

    assert mtd.resolver_nome_filial_tonelada("Timon") == (
        "COMERCIAL FERRONORTE LTDA-F09-TIMON"
    )


def test_resolver_nome_filial_tonelada_nao_encontrada(monkeypatch):
    monkeypatch.setattr(
        mtd, "carregar_meta_tonelada", lambda: _dados_teste()
    )

    with pytest.raises(ValueError):
        mtd.resolver_nome_filial_tonelada("Filial Que Nao Existe Xyz")


def test_construir_lista_rca_tonelada(monkeypatch):
    monkeypatch.setattr(
        mtd, "carregar_meta_tonelada", lambda: _dados_teste()
    )

    lista = mtd.construir_lista_rca_tonelada()

    nomes = {item["nome"] for item in lista}
    assert nomes == {"AURORA ANDRADE-F01", "JUNIOR PEREIRA-F01"}


def test_resolver_nomes_rca_tonelada_encontra_unico(monkeypatch):
    monkeypatch.setattr(
        mtd, "carregar_meta_tonelada", lambda: _dados_teste()
    )

    assert mtd.resolver_nomes_rca_tonelada("Aurora Andrade") == [
        "AURORA ANDRADE-F01"
    ]


def test_resolver_nomes_rca_tonelada_nao_encontrado(monkeypatch):
    monkeypatch.setattr(
        mtd, "carregar_meta_tonelada", lambda: _dados_teste()
    )

    with pytest.raises(ValueError):
        mtd.resolver_nomes_rca_tonelada("Vendedor Inexistente Xyz")


def test_resolver_nomes_rca_tonelada_ambiguo_sem_filial_soma(monkeypatch):
    monkeypatch.setattr(
        mtd,
        "construir_lista_rca_tonelada",
        lambda: [
            {"nome": "JOAO SILVA-F01", "filial": "FILIAL A"},
            {"nome": "JOAO SILVA-F02", "filial": "FILIAL B"},
        ],
    )

    nomes = mtd.resolver_nomes_rca_tonelada("Joao Silva")

    assert sorted(nomes) == ["JOAO SILVA-F01", "JOAO SILVA-F02"]


def test_resolver_nomes_rca_tonelada_ambiguo_com_filial_desambigua(
    monkeypatch,
):
    monkeypatch.setattr(
        mtd,
        "construir_lista_rca_tonelada",
        lambda: [
            {"nome": "JOAO SILVA-F01", "filial": "FILIAL A"},
            {"nome": "JOAO SILVA-F02", "filial": "FILIAL B"},
        ],
    )

    nomes = mtd.resolver_nomes_rca_tonelada(
        "Joao Silva",
        filiais=["FILIAL B"],
    )

    assert nomes == ["JOAO SILVA-F02"]
