from src import nps_tools as nt


def test_executar_consulta_indicadores_nps_repassa_agrupar_por_filial(
    monkeypatch,
):
    chamadas = []

    monkeypatch.setattr(
        nt,
        "consultar_indicadores_nps",
        lambda **kwargs: chamadas.append(kwargs) or {"resultados": []},
    )

    nt.executar_consulta_indicadores_nps(
        {
            "agrupar_por_filial": True,
            "periodos": [
                {
                    "data_inicial": "2026-01-01",
                    "data_final": "2026-12-31",
                }
            ],
        }
    )

    assert chamadas[0]["agrupar_por_filial"] is True
    assert chamadas[0]["filiais"] is None


def test_executar_consulta_indicadores_nps_repassa_agrupar_por_ano(
    monkeypatch,
):
    chamadas = []

    monkeypatch.setattr(
        nt,
        "obter_nps_por_filial",
        lambda: [{"filial": "FERRONORTE TIMON"}],
    )
    monkeypatch.setattr(
        nt,
        "consultar_indicadores_nps",
        lambda **kwargs: chamadas.append(kwargs) or {"resultados": []},
    )

    nt.executar_consulta_indicadores_nps(
        {
            "filiais": ["Timon"],
            "agrupar_por_ano": True,
        }
    )

    assert chamadas[0]["agrupar_por_ano"] is True
    assert chamadas[0]["filiais"] == ["FERRONORTE TIMON"]


def test_executar_consultar_evolucao_nps_repassa_anos(monkeypatch):
    chamadas = []

    monkeypatch.setattr(
        nt,
        "obter_evolucao_nps_por_filial",
        lambda **kwargs: chamadas.append(kwargs) or [],
    )

    resultado = nt.executar_consultar_evolucao_nps(
        {"ano_inicial": 2024, "ano_final": 2025}
    )

    assert chamadas[0]["ano_inicial"] == 2024
    assert chamadas[0]["ano_final"] == 2025
    assert chamadas[0]["filiais"] is None
    assert resultado["encontrado"] is False


def test_executar_consultar_evolucao_nps_resolve_filiais(monkeypatch):
    chamadas = []

    monkeypatch.setattr(
        nt,
        "obter_nps_por_filial",
        lambda: [{"filial": "FERRONORTE TIMON"}],
    )
    monkeypatch.setattr(
        nt,
        "obter_evolucao_nps_por_filial",
        lambda **kwargs: chamadas.append(kwargs)
        or [{"filial": "FERRONORTE TIMON", "diferenca": 5.0}],
    )

    resultado = nt.executar_consultar_evolucao_nps(
        {
            "ano_inicial": 2024,
            "ano_final": 2025,
            "filiais": ["Timon"],
        }
    )

    assert chamadas[0]["filiais"] == ["FERRONORTE TIMON"]
    assert resultado["encontrado"] is True


def test_executar_consulta_indicadores_nps_repassa_agrupar_por_mes(
    monkeypatch,
):
    chamadas = []

    monkeypatch.setattr(
        nt,
        "obter_nps_por_filial",
        lambda: [{"filial": "FERRONORTE TIMON"}],
    )
    monkeypatch.setattr(
        nt,
        "consultar_indicadores_nps",
        lambda **kwargs: chamadas.append(kwargs) or {"resultados": []},
    )

    nt.executar_consulta_indicadores_nps(
        {
            "filiais": ["Timon"],
            "agrupar_por_mes": True,
            "ano": 2025,
        }
    )

    assert chamadas[0]["agrupar_por_mes"] is True
    assert chamadas[0]["ano"] == 2025


def test_executar_consulta_indicadores_nps_padrao_nao_agrupa(
    monkeypatch,
):
    chamadas = []

    monkeypatch.setattr(
        nt,
        "consultar_indicadores_nps",
        lambda **kwargs: chamadas.append(kwargs) or {"resultados": []},
    )

    nt.executar_consulta_indicadores_nps({})

    assert chamadas[0]["agrupar_por_filial"] is False
