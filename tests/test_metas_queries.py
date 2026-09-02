from datetime import date

import pandas as pd

from src import metas_queries as mq


def _dados_teste():
    return pd.DataFrame(
        [
            {
                "FILIAL": "FERRONORTE TIMON",
                "COD_RCA": 8403,
                "COD_SUPERVISOR": 9,
                "MES": 7,
                "ANO": 2025,
                "VENDA_LIQ": 80000.0,
                "VALOR_META": 100000.0,
            },
            {
                "FILIAL": "FERRONORTE TIMON",
                "COD_RCA": 8471,
                "COD_SUPERVISOR": 9,
                "MES": 7,
                "ANO": 2025,
                "VENDA_LIQ": 60000.0,
                "VALOR_META": 50000.0,
            },
            {
                "FILIAL": "FERRONORTE TIBIRI",
                "COD_RCA": 9138,
                "COD_SUPERVISOR": 11,
                "MES": 7,
                "ANO": 2025,
                "VENDA_LIQ": 20000.0,
                "VALOR_META": 40000.0,
            },
        ]
    )


def test_consultar_metas_sem_dado_retorna_nao_encontrado(monkeypatch):
    monkeypatch.setattr(
        mq, "carregar_faturamento_8280", lambda: _dados_teste()
    )

    resultado = mq.consultar_metas(anos=[2019])

    assert resultado["encontrado"] is False
    assert "filtros_aplicados" in resultado


def test_consultar_metas_sem_agrupamento_soma_tudo(monkeypatch):
    monkeypatch.setattr(
        mq, "carregar_faturamento_8280", lambda: _dados_teste()
    )

    resultado = mq.consultar_metas(
        filiais=["FERRONORTE TIMON"],
        meses=[7],
        anos=[2025],
    )

    assert resultado["encontrado"] is True
    assert resultado["valor_meta"] == 150000.0
    assert resultado["faturamento_realizado"] == 140000.0
    assert resultado["falta_para_meta"] == 10000.0
    assert resultado["percentual_atingimento"] == round(
        140000 / 150000 * 100, 2
    )


def test_consultar_metas_falta_negativa_quando_meta_superada(monkeypatch):
    monkeypatch.setattr(
        mq, "carregar_faturamento_8280", lambda: _dados_teste()
    )

    resultado = mq.consultar_metas(
        rcas=[8471],
        meses=[7],
        anos=[2025],
    )

    assert resultado["valor_meta"] == 50000.0
    assert resultado["faturamento_realizado"] == 60000.0
    assert resultado["falta_para_meta"] == -10000.0
    assert resultado["percentual_atingimento"] == 120.0


def test_consultar_metas_agrupado_por_filial(monkeypatch):
    monkeypatch.setattr(
        mq, "carregar_faturamento_8280", lambda: _dados_teste()
    )
    monkeypatch.setattr(mq, "construir_mapa_rca_nome", lambda: {})
    monkeypatch.setattr(mq, "construir_lista_supervisores", lambda: [])

    resultado = mq.consultar_metas(
        meses=[7],
        anos=[2025],
        agrupar_por=["filial"],
    )

    assert resultado["encontrado"] is True
    filiais_no_resultado = {
        item["filial"] for item in resultado["resultados"]
    }
    assert filiais_no_resultado == {
        "FERRONORTE TIMON",
        "FERRONORTE TIBIRI",
    }


def test_consultar_metas_agrupado_por_supervisor_traz_nome(monkeypatch):
    monkeypatch.setattr(
        mq, "carregar_faturamento_8280", lambda: _dados_teste()
    )
    monkeypatch.setattr(
        mq,
        "construir_lista_supervisores",
        lambda: [
            {"codigo": 9, "nome": "SUPERVISOR COM F09 TIMON"},
            {"codigo": 11, "nome": "SUPERVISOR COM F11 IMPERATRIZ"},
        ],
    )

    resultado = mq.consultar_metas(
        meses=[7],
        anos=[2025],
        agrupar_por=["supervisor"],
    )

    item_supervisor_9 = next(
        item
        for item in resultado["resultados"]
        if item["supervisor"] == 9
    )
    assert item_supervisor_9["supervisor_nome"] == (
        "SUPERVISOR COM F09 TIMON"
    )


def test_calcular_dias_uteis_restantes_mes_atual(monkeypatch):
    class DataFalsa(date):
        @classmethod
        def today(cls):
            return date(2026, 8, 26)

    monkeypatch.setattr(mq, "date", DataFalsa)

    dias = mq._calcular_dias_uteis_restantes(2026, 8)

    assert dias == 4


def test_calcular_dias_uteis_restantes_mes_diferente_retorna_none(
    monkeypatch,
):
    class DataFalsa(date):
        @classmethod
        def today(cls):
            return date(2026, 8, 26)

    monkeypatch.setattr(mq, "date", DataFalsa)

    assert mq._calcular_dias_uteis_restantes(2025, 7) is None


def test_consultar_metas_inclui_necessidade_diaria_no_mes_atual(
    monkeypatch,
):
    class DataFalsa(date):
        @classmethod
        def today(cls):
            return date(2026, 8, 26)

    monkeypatch.setattr(mq, "date", DataFalsa)
    monkeypatch.setattr(
        mq,
        "carregar_faturamento_8280",
        lambda: pd.DataFrame(
            [
                {
                    "FILIAL": "FERRONORTE TIMON",
                    "COD_RCA": 8403,
                    "COD_SUPERVISOR": 9,
                    "MES": 8,
                    "ANO": 2026,
                    "VENDA_LIQ": 80000.0,
                    "VALOR_META": 100000.0,
                }
            ]
        ),
    )

    resultado = mq.consultar_metas(meses=[8], anos=[2026])

    assert resultado["necessidade_diaria"] == round(20000.0 / 4, 2)


def _dados_crescimento_abaixo_meta():
    return pd.DataFrame(
        [
            # FILIAL A: cresceu (100k -> 120k) e ficou abaixo da
            # meta em 2025 (120k / 150k = 80%) -> deve aparecer.
            {
                "FILIAL": "FILIAL A",
                "COD_RCA": 1,
                "COD_SUPERVISOR": 1,
                "MES": 1,
                "ANO": 2024,
                "VENDA_LIQ": 100000.0,
                "VALOR_META": 100000.0,
            },
            {
                "FILIAL": "FILIAL A",
                "COD_RCA": 1,
                "COD_SUPERVISOR": 1,
                "MES": 1,
                "ANO": 2025,
                "VENDA_LIQ": 120000.0,
                "VALOR_META": 150000.0,
            },
            # FILIAL B: cresceu (100k -> 150k) mas JÁ bateu a meta em
            # 2025 (150k / 100k = 150%) -> NÃO deve aparecer.
            {
                "FILIAL": "FILIAL B",
                "COD_RCA": 2,
                "COD_SUPERVISOR": 1,
                "MES": 1,
                "ANO": 2024,
                "VENDA_LIQ": 100000.0,
                "VALOR_META": 100000.0,
            },
            {
                "FILIAL": "FILIAL B",
                "COD_RCA": 2,
                "COD_SUPERVISOR": 1,
                "MES": 1,
                "ANO": 2025,
                "VENDA_LIQ": 150000.0,
                "VALOR_META": 100000.0,
            },
            # FILIAL C: caiu (200k -> 150k) -> NÃO deve aparecer,
            # mesmo estando abaixo da meta.
            {
                "FILIAL": "FILIAL C",
                "COD_RCA": 3,
                "COD_SUPERVISOR": 1,
                "MES": 1,
                "ANO": 2024,
                "VENDA_LIQ": 200000.0,
                "VALOR_META": 200000.0,
            },
            {
                "FILIAL": "FILIAL C",
                "COD_RCA": 3,
                "COD_SUPERVISOR": 1,
                "MES": 1,
                "ANO": 2025,
                "VENDA_LIQ": 150000.0,
                "VALOR_META": 200000.0,
            },
            # FILIAL D: só tem dado em 2025 (sem ano anterior) -> NÃO
            # deve aparecer, não dá pra calcular crescimento.
            {
                "FILIAL": "FILIAL D",
                "COD_RCA": 4,
                "COD_SUPERVISOR": 1,
                "MES": 1,
                "ANO": 2025,
                "VENDA_LIQ": 80000.0,
                "VALOR_META": 100000.0,
            },
            # FILIAL E: cresceu (50k -> 80k) mas sem meta cadastrada
            # em 2025 (VALOR_META 0) -> vai pra lista separada.
            {
                "FILIAL": "FILIAL E",
                "COD_RCA": 5,
                "COD_SUPERVISOR": 1,
                "MES": 1,
                "ANO": 2024,
                "VENDA_LIQ": 50000.0,
                "VALOR_META": 0.0,
            },
            {
                "FILIAL": "FILIAL E",
                "COD_RCA": 5,
                "COD_SUPERVISOR": 1,
                "MES": 1,
                "ANO": 2025,
                "VENDA_LIQ": 80000.0,
                "VALOR_META": 0.0,
            },
        ]
    )


def test_consultar_crescimento_abaixo_meta_filtra_corretamente(
    monkeypatch,
):
    monkeypatch.setattr(
        mq,
        "carregar_faturamento_8280",
        lambda: _dados_crescimento_abaixo_meta(),
    )
    monkeypatch.setattr(mq, "construir_mapa_rca_nome", lambda: {})
    monkeypatch.setattr(mq, "construir_lista_supervisores", lambda: [])

    resultado = mq.consultar_crescimento_abaixo_meta(ano=2025)

    assert resultado["encontrado"] is True

    filiais_no_resultado = {
        item["filial"] for item in resultado["resultados"]
    }
    assert filiais_no_resultado == {"FILIAL A"}

    item_a = resultado["resultados"][0]
    assert item_a["faturamento_realizado_ano_anterior"] == 100000.0
    assert item_a["faturamento_realizado"] == 120000.0
    assert item_a["crescimento_valor"] == 20000.0
    assert item_a["percentual_atingimento"] == 80.0

    filiais_sem_meta = {
        item["filial"]
        for item in resultado["cresceram_sem_meta_cadastrada"]
    }
    assert filiais_sem_meta == {"FILIAL E"}


def test_consultar_crescimento_abaixo_meta_sem_dado_ano_atual(
    monkeypatch,
):
    monkeypatch.setattr(
        mq, "carregar_faturamento_8280", lambda: _dados_teste()
    )

    resultado = mq.consultar_crescimento_abaixo_meta(ano=2019)

    assert resultado["encontrado"] is False


def test_consultar_metas_sem_necessidade_diaria_fora_do_mes_atual(
    monkeypatch,
):
    class DataFalsa(date):
        @classmethod
        def today(cls):
            return date(2026, 8, 26)

    monkeypatch.setattr(mq, "date", DataFalsa)
    monkeypatch.setattr(
        mq, "carregar_faturamento_8280", lambda: _dados_teste()
    )

    resultado = mq.consultar_metas(meses=[7], anos=[2025])

    assert "necessidade_diaria" not in resultado
