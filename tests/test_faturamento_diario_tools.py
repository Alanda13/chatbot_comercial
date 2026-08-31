import pytest

from src import faturamento_diario_tools as fdt


def test_executar_consulta_sem_periodo_gera_erro():
    with pytest.raises(ValueError):
        fdt.executar_consulta_indicadores_faturamento_diario({})


def test_executar_consulta_resolve_filial_e_repassa_periodo(monkeypatch):
    chamadas = []

    def fake_consulta(**kwargs):
        chamadas.append(kwargs)
        return {"encontrado": True, "faturamento": 100.0}

    monkeypatch.setattr(
        fdt,
        "resolver_nome_filial_diario",
        lambda nome: "FERRONORTE TIMON",
    )
    monkeypatch.setattr(
        fdt,
        "consultar_indicadores_faturamento_diario",
        fake_consulta,
    )

    resultado = fdt.executar_consulta_indicadores_faturamento_diario(
        {
            "filiais": ["Timon"],
            "periodos": [
                {"data_inicial": "2026-08-25", "data_final": "2026-08-25"}
            ],
        }
    )

    assert resultado == {"encontrado": True, "faturamento": 100.0}
    assert chamadas[0]["filiais"] == ["FERRONORTE TIMON"]
    assert chamadas[0]["data_inicial"] == "2026-08-25"


def test_executar_consulta_resolve_rca_por_nome(monkeypatch):
    chamadas = []

    def fake_consulta(**kwargs):
        chamadas.append(kwargs)
        return {"encontrado": True, "faturamento": 100.0}

    monkeypatch.setattr(
        fdt,
        "resolver_codigo_rca",
        lambda nome, filiais=None: 1901,
    )
    monkeypatch.setattr(
        fdt,
        "construir_mapa_rca_nome",
        lambda: {1901: "Alfredo Sousa-F09"},
    )
    monkeypatch.setattr(
        fdt,
        "consultar_indicadores_faturamento_diario",
        fake_consulta,
    )

    resultado = fdt.executar_consulta_indicadores_faturamento_diario(
        {
            "rcas": ["Alfredo Sousa"],
            "periodos": [
                {"data_inicial": "2026-08-25", "data_final": "2026-08-25"}
            ],
        }
    )

    assert chamadas[0]["rcas"] == [1901]
    assert resultado["filtros_aplicados"]["rcas_identificados"] == [
        "Alfredo Sousa-F09 (código 1901)"
    ]


def test_executar_consulta_com_varios_periodos_retorna_lista(monkeypatch):
    resultados_falsos = iter(
        [
            {"encontrado": True, "faturamento": 100.0},
            {"encontrado": True, "faturamento": 200.0},
        ]
    )

    monkeypatch.setattr(
        fdt,
        "consultar_indicadores_faturamento_diario",
        lambda **kwargs: next(resultados_falsos),
    )

    resultado = fdt.executar_consulta_indicadores_faturamento_diario(
        {
            "periodos": [
                {"data_inicial": "2026-08-25", "data_final": "2026-08-25"},
                {"data_inicial": "2026-08-26", "data_final": "2026-08-26"},
            ],
        }
    )

    assert resultado["periodos"] == [
        {"encontrado": True, "faturamento": 100.0},
        {"encontrado": True, "faturamento": 200.0},
    ]
