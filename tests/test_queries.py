from src import queries as q


def test_consultar_indicadores_nps_agrupar_por_filial_sem_periodo(
    monkeypatch,
):
    dados_fixos = [
        {"filial": "FERRONORTE TIMON", "nps": 80.0},
        {"filial": "FERRONORTE TIBIRI", "nps": 60.0},
    ]

    monkeypatch.setattr(
        q, "obter_nps_por_filial", lambda: dados_fixos
    )

    resultado = q.consultar_indicadores_nps(
        agrupar_por_filial=True,
    )

    assert resultado["filiais"] is None
    assert resultado["resultados"] == dados_fixos


def test_consultar_indicadores_nps_agrupar_por_filial_com_periodo(
    monkeypatch,
):
    monkeypatch.setattr(
        q,
        "obter_nps_por_filial",
        lambda: [
            {"filial": "FERRONORTE TIMON"},
            {"filial": "FERRONORTE TIBIRI"},
        ],
    )

    chamadas = []

    def obter_falso(filial, data_inicial, data_final):
        chamadas.append((filial, data_inicial, data_final))
        return {
            "filial": filial,
            "data_inicial": data_inicial,
            "data_final": data_final,
            "nps": 70.0,
        }

    monkeypatch.setattr(
        q, "obter_nps_filial_periodo", obter_falso
    )

    resultado = q.consultar_indicadores_nps(
        periodos=[
            {
                "data_inicial": "2026-01-01",
                "data_final": "2026-12-31",
            }
        ],
        agrupar_por_filial=True,
    )

    assert resultado["filiais"] == [
        "FERRONORTE TIMON",
        "FERRONORTE TIBIRI",
    ]
    assert len(resultado["resultados"]) == 2
    assert len(chamadas) == 2


def test_consultar_indicadores_nps_sem_agrupar_continua_agregado(
    monkeypatch,
):
    monkeypatch.setattr(
        q,
        "obter_nps_por_periodo",
        lambda data_inicial, data_final: {
            "nps": 87.79,
            "data_inicial": data_inicial,
            "data_final": data_final,
        },
    )

    resultado = q.consultar_indicadores_nps(
        periodos=[
            {
                "data_inicial": "2026-01-01",
                "data_final": "2026-12-31",
            }
        ],
    )

    assert resultado["filiais"] is None
    assert resultado["periodos"][0]["nps"] == 87.79
