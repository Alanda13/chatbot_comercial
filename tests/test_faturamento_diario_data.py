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
        "construir_lista_rca",
        lambda: [
            {
                "codigo": 1901,
                "nome": "Alfredo Sousa-F09",
                "filial": "FERRONORTE TIMON",
            }
        ],
    )

    assert fdd.resolver_codigo_rca("Alfredo Sousa") == 1901


def test_resolver_codigo_rca_nao_encontrado(monkeypatch):
    monkeypatch.setattr(
        fdd,
        "construir_lista_rca",
        lambda: [
            {
                "codigo": 1901,
                "nome": "Alfredo Sousa-F09",
                "filial": "FERRONORTE TIMON",
            }
        ],
    )

    with pytest.raises(ValueError):
        fdd.resolver_codigo_rca("Vendedor Inexistente")


def test_resolver_codigo_rca_ambiguo_gera_erro_com_codigo_e_filial(
    monkeypatch,
):
    monkeypatch.setattr(
        fdd,
        "construir_lista_rca",
        lambda: [
            {
                "codigo": 8952,
                "nome": "ANDRE ALVES-F09",
                "filial": "FERRONORTE TIMON",
            },
            {
                "codigo": 4521,
                "nome": "ANDRE ALVES-F18",
                "filial": "FERRONORTE IMPERATRIZ",
            },
        ],
    )

    with pytest.raises(ValueError) as excecao:
        fdd.resolver_codigo_rca("Andre Alves")

    mensagem = str(excecao.value)
    assert "8952" in mensagem
    assert "4521" in mensagem
    assert "FERRONORTE TIMON" in mensagem
    assert "FERRONORTE IMPERATRIZ" in mensagem


def test_resolver_codigo_rca_desambigua_pela_filial(monkeypatch):
    monkeypatch.setattr(
        fdd,
        "construir_lista_rca",
        lambda: [
            {
                "codigo": 8952,
                "nome": "ANDRE ALVES-F09",
                "filial": "FERRONORTE TIMON",
            },
            {
                "codigo": 4521,
                "nome": "ANDRE ALVES-F18",
                "filial": "FERRONORTE IMPERATRIZ",
            },
        ],
    )

    codigo = fdd.resolver_codigo_rca(
        "Andre Alves",
        filiais=["FERRONORTE TIMON"],
    )

    assert codigo == 8952


def test_resolver_codigo_rca_ainda_ambiguo_mesmo_com_filial(monkeypatch):
    monkeypatch.setattr(
        fdd,
        "construir_lista_rca",
        lambda: [
            {
                "codigo": 8952,
                "nome": "ANDRE ALVES-F09",
                "filial": "FERRONORTE TIMON",
            },
            {
                "codigo": 4521,
                "nome": "ANDRE ALVES-F18",
                "filial": "FERRONORTE IMPERATRIZ",
            },
        ],
    )

    with pytest.raises(ValueError):
        fdd.resolver_codigo_rca(
            "Andre Alves",
            filiais=["FERRONORTE ARAGUAINA"],
        )
