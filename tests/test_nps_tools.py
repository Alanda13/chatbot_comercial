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
