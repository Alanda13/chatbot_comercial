import pandas as pd
import pytest

from src import metas_data as md


def test_construir_lista_supervisores(monkeypatch):
    df = pd.DataFrame(
        [
            {
                "COD_SUPERVISOR": 1,
                "NOME_SUPERVISOR": "SUPERVISOR COM F01 MATRIZ",
                "FILIAL": "FERRONORTE TIMON",
            },
            {
                "COD_SUPERVISOR": 1,
                "NOME_SUPERVISOR": "SUPERVISOR COM F01 MATRIZ",
                "FILIAL": "FERRONORTE TIMON",
            },
            {
                "COD_SUPERVISOR": 9,
                "NOME_SUPERVISOR": "SUPERVISOR COM F09 TIMON",
                "FILIAL": "FERRONORTE TIMON",
            },
        ]
    )
    monkeypatch.setattr(md, "carregar_faturamento_8280", lambda: df)

    lista = md.construir_lista_supervisores()

    assert len(lista) == 2
    codigos = {item["codigo"] for item in lista}
    assert codigos == {1, 9}


def test_resolver_codigos_supervisor_com_codigo_numerico(monkeypatch):
    monkeypatch.setattr(
        md,
        "construir_lista_supervisores",
        lambda: [
            {
                "codigo": 9,
                "nome": "SUPERVISOR COM F09 TIMON",
                "filial": "FERRONORTE TIMON",
            }
        ],
    )

    assert md.resolver_codigos_supervisor(9) == [9]
    assert md.resolver_codigos_supervisor("9") == [9]


def test_resolver_codigos_supervisor_codigo_inexistente(monkeypatch):
    monkeypatch.setattr(
        md,
        "construir_lista_supervisores",
        lambda: [
            {
                "codigo": 9,
                "nome": "SUPERVISOR COM F09 TIMON",
                "filial": "FERRONORTE TIMON",
            }
        ],
    )

    with pytest.raises(ValueError):
        md.resolver_codigos_supervisor(999)


def test_resolver_codigos_supervisor_por_nome(monkeypatch):
    monkeypatch.setattr(
        md,
        "construir_lista_supervisores",
        lambda: [
            {
                "codigo": 9,
                "nome": "SUPERVISOR COM F09 TIMON",
                "filial": "FERRONORTE TIMON",
            }
        ],
    )

    assert md.resolver_codigos_supervisor("Supervisor Com F09 Timon") == [9]


def test_resolver_codigos_supervisor_ambiguo_sem_filial_soma(monkeypatch):
    monkeypatch.setattr(
        md,
        "construir_lista_supervisores",
        lambda: [
            {
                "codigo": 1,
                "nome": "JOAO SILVA-F01",
                "filial": "FERRONORTE TIMON",
            },
            {
                "codigo": 2,
                "nome": "JOAO SILVA-F02",
                "filial": "FERRONORTE TIBIRI",
            },
        ],
    )

    codigos = md.resolver_codigos_supervisor("Joao Silva")

    assert sorted(codigos) == [1, 2]


def test_resolver_codigos_supervisor_ambiguo_com_filial_desambigua(
    monkeypatch,
):
    monkeypatch.setattr(
        md,
        "construir_lista_supervisores",
        lambda: [
            {
                "codigo": 1,
                "nome": "JOAO SILVA-F01",
                "filial": "FERRONORTE TIMON",
            },
            {
                "codigo": 2,
                "nome": "JOAO SILVA-F02",
                "filial": "FERRONORTE TIBIRI",
            },
        ],
    )

    codigos = md.resolver_codigos_supervisor(
        "Joao Silva",
        filiais=["FERRONORTE TIBIRI"],
    )

    assert codigos == [2]


def test_resolver_codigos_supervisor_nao_encontrado(monkeypatch):
    monkeypatch.setattr(
        md,
        "construir_lista_supervisores",
        lambda: [
            {
                "codigo": 9,
                "nome": "SUPERVISOR COM F09 TIMON",
                "filial": "FERRONORTE TIMON",
            }
        ],
    )

    with pytest.raises(ValueError):
        md.resolver_codigos_supervisor("Fulano Inexistente")
