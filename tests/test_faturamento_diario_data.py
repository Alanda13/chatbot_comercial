import pandas as pd

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
