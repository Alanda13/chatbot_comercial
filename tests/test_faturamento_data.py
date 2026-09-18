import pandas as pd
import pytest

from src import faturamento_data as fd


@pytest.fixture
def dados_faturamento(monkeypatch):
    df = pd.DataFrame(
        [
            {"FILIAL": "FERRONORTE TIMON", "COD_RCA": 1901},
            {"FILIAL": "FERRONORTE PICOS", "COD_RCA": 1902},
        ]
    )
    monkeypatch.setattr(fd, "carregar_faturamento_8280", lambda: df)
    return df


def test_listar_filiais_faturamento(dados_faturamento):
    filiais = fd.listar_filiais_faturamento()

    assert filiais == ["FERRONORTE PICOS", "FERRONORTE TIMON"]
