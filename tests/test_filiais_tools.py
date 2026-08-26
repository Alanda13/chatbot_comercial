from src import filiais_tools


def test_executar_listar_filiais(monkeypatch):
    monkeypatch.setattr(
        filiais_tools,
        "listar_filiais_faturamento",
        lambda: ["FERRONORTE PICOS", "FERRONORTE TIMON"],
    )

    resultado = filiais_tools.executar_listar_filiais({})

    assert resultado == {
        "quantidade_filiais": 2,
        "filiais": ["FERRONORTE PICOS", "FERRONORTE TIMON"],
    }
