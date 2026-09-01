from src import meta_tonelada_tools as mtt


def test_executar_consultar_meta_tonelada_repassa_filtros_simples(
    monkeypatch,
):
    chamadas = []

    monkeypatch.setattr(
        mtt,
        "consultar_meta_tonelada",
        lambda **kwargs: chamadas.append(kwargs)
        or {"encontrado": True},
    )

    mtt.executar_consultar_meta_tonelada({"anos": [2025]})

    assert chamadas[0]["anos"] == [2025]
    assert chamadas[0]["filiais"] is None
    assert chamadas[0]["rcas"] is None


def test_executar_consultar_meta_tonelada_resolve_filial_e_rca(
    monkeypatch,
):
    chamadas = []

    monkeypatch.setattr(
        mtt,
        "resolver_nome_filial_tonelada",
        lambda nome: "COMERCIAL FERRONORTE LTDA-F09-TIMON",
    )
    monkeypatch.setattr(
        mtt,
        "resolver_nomes_rca_tonelada",
        lambda nome, filiais=None: ["AURORA ANDRADE-F09"],
    )
    monkeypatch.setattr(
        mtt,
        "consultar_meta_tonelada",
        lambda **kwargs: chamadas.append(kwargs)
        or {"encontrado": True},
    )

    mtt.executar_consultar_meta_tonelada(
        {
            "filiais": ["Timon"],
            "rcas": ["Aurora Andrade"],
            "anos": [2025],
        }
    )

    assert chamadas[0]["filiais"] == [
        "COMERCIAL FERRONORTE LTDA-F09-TIMON"
    ]
    assert chamadas[0]["rcas"] == ["AURORA ANDRADE-F09"]
