from src import metas_tools as mt


def test_executar_consultar_metas_repassa_filtros_simples(monkeypatch):
    chamadas = []

    monkeypatch.setattr(
        mt,
        "consultar_metas",
        lambda **kwargs: chamadas.append(kwargs) or {"encontrado": True},
    )

    mt.executar_consultar_metas({"meses": [7], "anos": [2025]})

    assert chamadas[0]["meses"] == [7]
    assert chamadas[0]["anos"] == [2025]
    assert chamadas[0]["filiais"] is None
    assert chamadas[0]["rcas"] is None
    assert chamadas[0]["supervisores"] is None


def test_executar_consultar_metas_resolve_filial_rca_e_supervisor(
    monkeypatch,
):
    chamadas = []

    monkeypatch.setattr(
        mt, "resolver_nome_filial", lambda nome: "FERRONORTE TIMON"
    )
    monkeypatch.setattr(
        mt,
        "resolver_codigos_rca",
        lambda nome, filiais=None: [8403],
    )
    monkeypatch.setattr(
        mt,
        "resolver_codigos_supervisor",
        lambda nome, filiais=None: [9],
    )
    monkeypatch.setattr(
        mt,
        "consultar_metas",
        lambda **kwargs: chamadas.append(kwargs) or {"encontrado": True},
    )

    mt.executar_consultar_metas(
        {
            "filiais": ["Timon"],
            "rcas": ["Alfredo Sousa"],
            "supervisores": ["Supervisor Com F09 Timon"],
            "anos": [2025],
        }
    )

    assert chamadas[0]["filiais"] == ["FERRONORTE TIMON"]
    assert chamadas[0]["rcas"] == [8403]
    assert chamadas[0]["supervisores"] == [9]


def test_executar_consultar_crescimento_abaixo_meta_repassa_ano(
    monkeypatch,
):
    chamadas = []

    monkeypatch.setattr(
        mt,
        "consultar_crescimento_abaixo_meta",
        lambda **kwargs: chamadas.append(kwargs) or {"encontrado": True},
    )

    mt.executar_consultar_crescimento_abaixo_meta({"ano": 2025})

    assert chamadas[0]["ano"] == 2025
    assert chamadas[0]["agrupar_por"] == "filial"
    assert chamadas[0]["filiais"] is None


def test_executar_consultar_crescimento_abaixo_meta_normaliza_lista(
    monkeypatch,
):
    chamadas = []

    monkeypatch.setattr(
        mt,
        "consultar_crescimento_abaixo_meta",
        lambda **kwargs: chamadas.append(kwargs) or {"encontrado": True},
    )

    mt.executar_consultar_crescimento_abaixo_meta(
        {"ano": 2025, "agrupar_por": ["rca"]}
    )

    assert chamadas[0]["agrupar_por"] == "rca"


def test_executar_consultar_crescimento_abaixo_meta_resolve_filial(
    monkeypatch,
):
    chamadas = []

    monkeypatch.setattr(
        mt, "resolver_nome_filial", lambda nome: "FERRONORTE TIMON"
    )
    monkeypatch.setattr(
        mt,
        "consultar_crescimento_abaixo_meta",
        lambda **kwargs: chamadas.append(kwargs) or {"encontrado": True},
    )

    mt.executar_consultar_crescimento_abaixo_meta(
        {"ano": 2025, "filiais": ["Timon"]}
    )

    assert chamadas[0]["filiais"] == ["FERRONORTE TIMON"]
