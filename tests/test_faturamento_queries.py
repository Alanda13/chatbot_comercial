import pandas as pd
import pytest

from src import faturamento_queries as fq


@pytest.fixture
def dados_faturamento(monkeypatch):
    df = pd.DataFrame(
        [
            {
                "FILIAL": "FERRONORTE TIMON",
                "COD_RCA": 1901,
                "MES": 7,
                "ANO": 2025,
                "VENDA_LIQ": 1000.0,
                "VENDA_BRUTA": 1200.0,
                "VALORDESC": 200.0,
                "PESOLIQ": 50.0,
                "QT_NOTAS": 3,
            },
            {
                "FILIAL": "FERRONORTE TIMON",
                "COD_RCA": 1901,
                "MES": 8,
                "ANO": 2025,
                "VENDA_LIQ": 500.0,
                "VENDA_BRUTA": 600.0,
                "VALORDESC": 100.0,
                "PESOLIQ": 20.0,
                "QT_NOTAS": 1,
            },
            {
                "FILIAL": "FERRONORTE PICOS",
                "COD_RCA": 1902,
                "MES": 7,
                "ANO": 2025,
                "VENDA_LIQ": 300.0,
                "VENDA_BRUTA": 350.0,
                "VALORDESC": 50.0,
                "PESOLIQ": 10.0,
                "QT_NOTAS": 2,
            },
        ]
    )
    monkeypatch.setattr(fq, "carregar_faturamento_8280", lambda: df)
    return df


def test_consulta_sem_filtros_soma_tudo(dados_faturamento):
    resultado = fq.consultar_indicadores_faturamento()

    assert resultado["encontrado"] is True
    assert resultado["faturamento"] == 1800.0
    assert resultado["quantidade_notas"] == 6


def test_consulta_filtrada_por_filial_e_periodo(dados_faturamento):
    resultado = fq.consultar_indicadores_faturamento(
        filiais=["FERRONORTE TIMON"],
        meses=[7],
        anos=[2025],
    )

    assert resultado["faturamento"] == 1000.0


def test_consulta_sem_dados_retorna_nao_encontrado(dados_faturamento):
    resultado = fq.consultar_indicadores_faturamento(
        filiais=["FILIAL INEXISTENTE"],
    )

    assert resultado["encontrado"] is False
    assert resultado["filtros_aplicados"]["filiais"] == ["FILIAL INEXISTENTE"]


def test_consulta_agrupada_por_filial(dados_faturamento):
    resultado = fq.consultar_indicadores_faturamento(
        anos=[2025],
        agrupar_por=["filial"],
    )

    valores = {
        item["filial"]: item["faturamento"]
        for item in resultado["resultados"]
    }

    assert valores["FERRONORTE TIMON"] == 1500.0
    assert valores["FERRONORTE PICOS"] == 300.0


def test_agrupamento_invalido_gera_erro(dados_faturamento):
    with pytest.raises(ValueError):
        fq.consultar_indicadores_faturamento(agrupar_por=["invalido"])


def test_consulta_agrupada_por_rca_inclui_nome(dados_faturamento, monkeypatch):
    monkeypatch.setattr(
        fq,
        "construir_mapa_rca_nome",
        lambda: {1901: "Jose Felipe Pires", 1902: "Maria Souza"},
    )

    resultado = fq.consultar_indicadores_faturamento(
        anos=[2025],
        agrupar_por=["rca"],
    )

    nomes = {
        item["rca"]: item["rca_nome"]
        for item in resultado["resultados"]
    }

    assert nomes[1901] == "Jose Felipe Pires"
    assert nomes[1902] == "Maria Souza"


def test_consulta_agrupada_por_rca_sem_arquivo_8302(
    dados_faturamento, monkeypatch
):
    def _levanta_erro():
        raise FileNotFoundError("arquivo não encontrado")

    monkeypatch.setattr(fq, "construir_mapa_rca_nome", _levanta_erro)

    resultado = fq.consultar_indicadores_faturamento(
        anos=[2025],
        agrupar_por=["rca"],
    )

    assert all(
        item["rca_nome"] is None for item in resultado["resultados"]
    )


def test_listar_filiais_faturamento(dados_faturamento):
    filiais = fq.listar_filiais_faturamento()

    assert filiais == ["FERRONORTE PICOS", "FERRONORTE TIMON"]
