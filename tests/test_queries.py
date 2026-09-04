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


def test_obter_evolucao_nps_por_filial_ordena_maior_pra_menor(
    monkeypatch,
):
    monkeypatch.setattr(
        q,
        "obter_nps_por_filial",
        lambda: [
            {"filial": "FERRONORTE TIMON"},
            {"filial": "FERRONORTE TIBIRI"},
            {"filial": "FERRONORTE IMPERATRIZ"},
        ],
    )

    valores = {
        ("FERRONORTE TIMON", "2024"): 80.0,
        ("FERRONORTE TIMON", "2025"): 85.0,
        ("FERRONORTE TIBIRI", "2024"): 90.0,
        ("FERRONORTE TIBIRI", "2025"): 70.0,
        ("FERRONORTE IMPERATRIZ", "2024"): 60.0,
        ("FERRONORTE IMPERATRIZ", "2025"): 90.0,
    }

    def obter_falso(filial, data_inicial, data_final):
        ano = data_inicial[:4]
        return {"filial": filial, "nps": valores[(filial, ano)]}

    monkeypatch.setattr(
        q, "obter_nps_filial_periodo", obter_falso
    )

    resultado = q.obter_evolucao_nps_por_filial(2024, 2025)

    assert [item["filial"] for item in resultado] == [
        "FERRONORTE IMPERATRIZ",
        "FERRONORTE TIMON",
        "FERRONORTE TIBIRI",
    ]
    assert resultado[0]["diferenca"] == 30.0
    assert resultado[-1]["diferenca"] == -20.0


def test_obter_evolucao_nps_por_filial_ignora_nps_nulo(monkeypatch):
    monkeypatch.setattr(
        q,
        "obter_nps_por_filial",
        lambda: [{"filial": "FERRONORTE SEM DADO"}],
    )
    monkeypatch.setattr(
        q,
        "obter_nps_filial_periodo",
        lambda filial, data_inicial, data_final: {
            "filial": filial,
            "nps": None,
        },
    )

    resultado = q.obter_evolucao_nps_por_filial(2024, 2025)

    assert resultado == []


def test_consultar_indicadores_nps_agrupar_por_mes_com_filial(
    monkeypatch,
):
    chamadas = []

    def obter_falso(filial, data_inicial, data_final):
        chamadas.append((filial, data_inicial, data_final))
        return {
            "filial": filial,
            "data_inicial": data_inicial,
            "data_final": data_final,
            "nps": 90.0,
        }

    monkeypatch.setattr(
        q, "obter_nps_filial_periodo", obter_falso
    )

    resultado = q.consultar_indicadores_nps(
        filiais=["FERRONORTE TIMON"],
        agrupar_por_mes=True,
        ano=2025,
    )

    assert resultado["filiais"] == ["FERRONORTE TIMON"]
    assert len(resultado["resultados"]) == 12
    assert chamadas[0] == (
        "FERRONORTE TIMON",
        "2025-01-01",
        "2025-01-31",
    )
    # Fevereiro de 2025 (não bissexto) deve ir até o dia 28.
    assert chamadas[1] == (
        "FERRONORTE TIMON",
        "2025-02-01",
        "2025-02-28",
    )


def test_consultar_indicadores_nps_agrupar_por_mes_empresa_inteira(
    monkeypatch,
):
    chamadas = []

    def obter_falso(data_inicial, data_final):
        chamadas.append((data_inicial, data_final))
        return {
            "data_inicial": data_inicial,
            "data_final": data_final,
            "nps": 50.0,
        }

    monkeypatch.setattr(
        q, "obter_nps_por_periodo", obter_falso
    )

    resultado = q.consultar_indicadores_nps(
        agrupar_por_mes=True,
        ano=2026,
    )

    assert resultado["filiais"] is None
    assert len(resultado["resultados"]) == 12
    # Fevereiro de 2026 (não bissexto) deve ir até o dia 28.
    assert chamadas[1] == ("2026-02-01", "2026-02-28")


def test_consultar_indicadores_nps_agrupar_por_ano_com_filial(
    monkeypatch,
):
    monkeypatch.setattr(
        q, "obter_anos_com_dados_nps", lambda: [2024, 2025, 2026]
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
        filiais=["FERRONORTE TIMON"],
        agrupar_por_ano=True,
    )

    assert resultado["filiais"] == ["FERRONORTE TIMON"]
    assert len(resultado["resultados"]) == 3
    assert chamadas[0] == (
        "FERRONORTE TIMON",
        "2024-01-01",
        "2024-12-31",
    )


def test_consultar_indicadores_nps_agrupar_por_ano_empresa_inteira(
    monkeypatch,
):
    monkeypatch.setattr(
        q, "obter_anos_com_dados_nps", lambda: [2025, 2026]
    )

    chamadas = []

    def obter_falso(data_inicial, data_final):
        chamadas.append((data_inicial, data_final))
        return {
            "data_inicial": data_inicial,
            "data_final": data_final,
            "nps": 50.0,
        }

    monkeypatch.setattr(
        q, "obter_nps_por_periodo", obter_falso
    )

    resultado = q.consultar_indicadores_nps(
        agrupar_por_ano=True,
    )

    assert resultado["filiais"] is None
    assert len(resultado["resultados"]) == 2


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
