from core.services.ferramentas import filiais_tools


def test_executar_listar_filiais():
    resultado = filiais_tools.executar_listar_filiais({})

    assert resultado["quantidade_filiais"] == 18
    assert "TIMON" in resultado["filiais"]
    assert "FN ATACADO" not in resultado["filiais"]
