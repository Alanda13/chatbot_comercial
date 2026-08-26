import pandas as pd
import pytest

from src import faturamento_diario_queries as fdq


@pytest.fixture
def dados_faturamento_diario(monkeypatch):
    df = pd.DataFrame(
        [
            {
                "FILIAL": "FERRONORTE TIMON",
                "DATA": pd.Timestamp("2026-08-25"),
                "COD_RCA": 1901,
                "VENDA_LIQ": 1000.0,
                "VENDA_BRUTA": 1200.0,
                "VALORDESC": 200.0,
                "QT_NOTAS": 3,
                "COBRANCA": "Dinheiro",
            },
            {
                "FILIAL": "FERRONORTE TIMON",
                "DATA": pd.Timestamp("2026-08-25"),
                "COD_RCA": 1901,
                "VENDA_LIQ": 500.0,
                "VENDA_BRUTA": 600.0,
                "VALORDESC": 100.0,
                "QT_NOTAS": 1,
                "COBRANCA": "CARTAO VISA DEBITO",
            },
            {
                "FILIAL": "FERRONORTE TIMON",
                "DATA": pd.Timestamp("2026-08-26"),
                "COD_RCA": 1901,
                "VENDA_LIQ": 300.0,
                "VENDA_BRUTA": 350.0,
                "VALORDESC": 50.0,
                "QT_NOTAS": 2,
                "COBRANCA": "Dinheiro",
            },
            {
                "FILIAL": "FERRONORTE PICOS",
                "DATA": pd.Timestamp("2026-08-25"),
                "COD_RCA": 1902,
                "VENDA_LIQ": 700.0,
                "VENDA_BRUTA": 800.0,
                "VALORDESC": 100.0,
                "QT_NOTAS": 4,
                "COBRANCA": "Dinheiro",
            },
        ]
    )
    monkeypatch.setattr(fdq, "carregar_faturamento_8302", lambda: df)
    return df


def test_consulta_periodo_de_um_dia(dados_faturamento_diario):
    resultado = fdq.consultar_indicadores_faturamento_diario(
        data_inicial="2026-08-25",
        data_final="2026-08-25",
        filiais=["FERRONORTE TIMON"],
    )

    assert resultado["encontrado"] is True
    assert resultado["faturamento"] == 1500.0
    assert resultado["quantidade_notas"] == 4


def test_consulta_periodo_de_varios_dias(dados_faturamento_diario):
    resultado = fdq.consultar_indicadores_faturamento_diario(
        data_inicial="2026-08-25",
        data_final="2026-08-26",
        filiais=["FERRONORTE TIMON"],
    )

    assert resultado["faturamento"] == 1800.0


def test_consulta_sem_dados_no_periodo(dados_faturamento_diario):
    resultado = fdq.consultar_indicadores_faturamento_diario(
        data_inicial="2026-01-01",
        data_final="2026-01-31",
        filiais=["FERRONORTE TIMON"],
    )

    assert resultado["encontrado"] is False
    assert resultado["filtros_aplicados"]["data_inicial"] == "2026-01-01"
    assert resultado["filtros_aplicados"]["filiais"] == ["FERRONORTE TIMON"]


def test_consulta_agrupada_por_dia(dados_faturamento_diario):
    resultado = fdq.consultar_indicadores_faturamento_diario(
        data_inicial="2026-08-25",
        data_final="2026-08-26",
        filiais=["FERRONORTE TIMON"],
        agrupar_por=["dia"],
    )

    valores = {
        item["dia"]: item["faturamento"]
        for item in resultado["resultados"]
    }

    assert valores["2026-08-25"] == 1500.0
    assert valores["2026-08-26"] == 300.0


def test_consulta_agrupada_por_forma_pagamento(dados_faturamento_diario):
    resultado = fdq.consultar_indicadores_faturamento_diario(
        data_inicial="2026-08-25",
        data_final="2026-08-25",
        filiais=["FERRONORTE TIMON"],
        agrupar_por=["forma_pagamento"],
    )

    valores = {
        item["forma_pagamento"]: item["faturamento"]
        for item in resultado["resultados"]
    }

    assert valores["Dinheiro"] == 1000.0
    assert valores["CARTAO VISA DEBITO"] == 500.0


def test_agrupamento_invalido_gera_erro(dados_faturamento_diario):
    with pytest.raises(ValueError):
        fdq.consultar_indicadores_faturamento_diario(
            data_inicial="2026-08-25",
            data_final="2026-08-26",
            agrupar_por=["invalido"],
        )


def test_listar_filiais_faturamento_diario(dados_faturamento_diario):
    filiais = fdq.listar_filiais_faturamento_diario()

    assert filiais == ["FERRONORTE PICOS", "FERRONORTE TIMON"]
