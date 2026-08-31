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


def test_resolver_codigos_rca_com_codigo_numerico(monkeypatch):
    monkeypatch.setattr(
        fdd,
        "construir_lista_rca",
        lambda: [
            {
                "codigo": 1901,
                "nome": "Jose Felipe Pires",
                "filial": "FERRONORTE TIMON",
            }
        ],
    )

    assert fdd.resolver_codigos_rca(1901) == [1901]
    assert fdd.resolver_codigos_rca("1901") == [1901]


def test_resolver_codigos_rca_com_codigo_numerico_inexistente(monkeypatch):
    monkeypatch.setattr(
        fdd,
        "construir_lista_rca",
        lambda: [
            {
                "codigo": 1901,
                "nome": "Jose Felipe Pires",
                "filial": "FERRONORTE TIMON",
            }
        ],
    )

    with pytest.raises(ValueError) as excecao:
        fdd.resolver_codigos_rca("896869")

    assert "896869" in str(excecao.value)


def test_resolver_codigos_rca_com_nome(monkeypatch):
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

    assert fdd.resolver_codigos_rca("Alfredo Sousa") == [1901]


def test_resolver_codigos_rca_nao_encontrado(monkeypatch):
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
        fdd.resolver_codigos_rca("Vendedor Inexistente")


def test_resolver_codigos_rca_sem_filial_soma_todos_os_candidatos(
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

    codigos = fdd.resolver_codigos_rca("Andre Alves")

    assert sorted(codigos) == [4521, 8952]


def test_resolver_codigos_rca_desambigua_pela_filial(monkeypatch):
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

    codigos = fdd.resolver_codigos_rca(
        "Andre Alves",
        filiais=["FERRONORTE TIMON"],
    )

    assert codigos == [8952]


def test_resolver_codigos_rca_ainda_ambiguo_mesmo_com_filial(monkeypatch):
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
        fdd.resolver_codigos_rca(
            "Andre Alves",
            filiais=["FERRONORTE ARAGUAINA"],
        )

    mensagem = str(excecao.value)
    assert "8952" in mensagem
    assert "4521" in mensagem


def test_verificar_rca_encontrado(monkeypatch):
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
    monkeypatch.setattr(
        fdd,
        "construir_mapa_rca_nome",
        lambda: {1901: "Alfredo Sousa-F09"},
    )

    resultado = fdd.verificar_rca("Alfredo Sousa")

    assert resultado["encontrado"] is True
    assert resultado["rcas_identificados"] == [
        "Alfredo Sousa-F09 (código 1901)"
    ]


def test_verificar_rca_nao_encontrado(monkeypatch):
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

    resultado = fdd.verificar_rca("4567")

    assert resultado["encontrado"] is False
    assert "4567" in resultado["mensagem"]
