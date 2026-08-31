import pandas as pd
import pytest

from src import faturamento_diario_data as fdd


def test_construir_mapa_rca_nome(monkeypatch):
    df = pd.DataFrame(
        [
            {"COD_RCA": 1901, "NOME_RCA": "Jose Felipe Pires"},
            {"COD_RCA": 1901, "NOME_RCA": "Jose Felipe Pires"},
            {"COD_RCA": 1902, "NOME_RCA": "Maria Souza"},
            {"COD_RCA": 1903, "NOME_RCA": None},
        ]
    )
    monkeypatch.setattr(fdd, "carregar_faturamento_8302", lambda: df)

    mapa = fdd.construir_mapa_rca_nome()

    assert mapa == {
        1901: "Jose Felipe Pires",
        1902: "Maria Souza",
    }


def test_resolver_codigo_rca_com_codigo_numerico():
    assert fdd.resolver_codigo_rca(1901) == 1901
    assert fdd.resolver_codigo_rca("1901") == 1901


def test_resolver_codigo_rca_com_nome(monkeypatch):
    monkeypatch.setattr(
        fdd,
        "construir_mapa_rca_nome",
        lambda: {1901: "Alfredo Sousa-F09"},
    )

    assert fdd.resolver_codigo_rca("Alfredo Sousa") == 1901


def test_resolver_codigo_rca_nao_encontrado(monkeypatch):
    monkeypatch.setattr(
        fdd,
        "construir_mapa_rca_nome",
        lambda: {1901: "Alfredo Sousa-F09"},
    )

    with pytest.raises(ValueError):
        fdd.resolver_codigo_rca("Vendedor Inexistente")


def test_resolver_codigo_rca_ambiguo_gera_erro(monkeypatch):
    monkeypatch.setattr(
        fdd,
        "construir_mapa_rca_nome",
        lambda: {
            8952: "ANDRE ALVES-F09",
            8998: "ANDREA ALVES - F09",
        },
    )

    with pytest.raises(ValueError):
        fdd.resolver_codigo_rca("Andre")
