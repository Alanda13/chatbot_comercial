from src import faturamento_tools as ft


def test_executar_consulta_resolve_rca_por_nome(monkeypatch):
    chamadas = []

    def fake_consulta(**kwargs):
        chamadas.append(kwargs)
        return {"encontrado": True, "faturamento": 100.0}

    monkeypatch.setattr(
        ft,
        "resolver_codigo_rca",
        lambda nome: 1901,
    )
    monkeypatch.setattr(
        ft,
        "consultar_indicadores_faturamento",
        fake_consulta,
    )

    ft.executar_consulta_indicadores_faturamento(
        {
            "rcas": ["Alfredo Sousa"],
            "anos": [2025],
        }
    )

    assert chamadas[0]["rcas"] == [1901]


def test_executar_consulta_sem_rca_nao_resolve(monkeypatch):
    chamadas = []

    monkeypatch.setattr(
        ft,
        "consultar_indicadores_faturamento",
        lambda **kwargs: chamadas.append(kwargs),
    )

    ft.executar_consulta_indicadores_faturamento({"anos": [2025]})

    assert chamadas[0]["rcas"] is None
