from src import faturamento_tools as ft


def test_executar_consulta_resolve_rca_por_nome(monkeypatch):
    chamadas = []

    def fake_consulta(**kwargs):
        chamadas.append(kwargs)
        return {"encontrado": True, "faturamento": 100.0}

    monkeypatch.setattr(
        ft,
        "resolver_codigo_rca",
        lambda nome, filiais=None: 1901,
    )
    monkeypatch.setattr(
        ft,
        "construir_mapa_rca_nome",
        lambda: {1901: "Alfredo Sousa-F09"},
    )
    monkeypatch.setattr(
        ft,
        "consultar_indicadores_faturamento",
        fake_consulta,
    )

    resultado = ft.executar_consulta_indicadores_faturamento(
        {
            "rcas": ["Alfredo Sousa"],
            "anos": [2025],
        }
    )

    assert chamadas[0]["rcas"] == [1901]
    assert resultado["filtros_aplicados"]["rcas_identificados"] == [
        "Alfredo Sousa-F09 (código 1901)"
    ]


def test_executar_consulta_passa_filial_resolvida_pro_resolver_rca(
    monkeypatch,
):
    chamadas_resolver = []

    monkeypatch.setattr(
        ft,
        "resolver_nome_filial",
        lambda nome: "FERRONORTE TIMON",
    )

    def fake_resolver(nome, filiais=None):
        chamadas_resolver.append(filiais)
        return 1901

    monkeypatch.setattr(ft, "resolver_codigo_rca", fake_resolver)
    monkeypatch.setattr(
        ft,
        "construir_mapa_rca_nome",
        lambda: {1901: "Andre Alves-F09"},
    )
    monkeypatch.setattr(
        ft,
        "consultar_indicadores_faturamento",
        lambda **kwargs: {"encontrado": True},
    )

    ft.executar_consulta_indicadores_faturamento(
        {
            "filiais": ["Timon"],
            "rcas": ["Andre Alves"],
            "anos": [2025],
        }
    )

    assert chamadas_resolver == [["FERRONORTE TIMON"]]


def test_executar_consulta_sem_rca_nao_resolve(monkeypatch):
    chamadas = []

    monkeypatch.setattr(
        ft,
        "consultar_indicadores_faturamento",
        lambda **kwargs: chamadas.append(kwargs),
    )

    ft.executar_consulta_indicadores_faturamento({"anos": [2025]})

    assert chamadas[0]["rcas"] is None
