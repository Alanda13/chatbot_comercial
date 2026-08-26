import pytest

from src import tool_manager
from src.exceptions import FerramentaError


def test_ferramenta_existe():
    assert tool_manager.ferramenta_existe("consultar_indicadores_nps") is True
    assert tool_manager.ferramenta_existe("nao_existe") is False


def test_executar_ferramenta_inexistente_gera_erro():
    with pytest.raises(FerramentaError):
        tool_manager.executar_ferramenta("nao_existe", {})


def test_executar_ferramenta_argumento_obrigatorio_ausente(monkeypatch):
    monkeypatch.setitem(
        tool_manager.FERRAMENTAS_DISPONIVEIS,
        "ferramenta_teste",
        {
            "descricao": "teste",
            "argumentos_obrigatorios": ["periodo"],
            "argumentos_opcionais": [],
            "funcao": lambda argumentos: argumentos,
        },
    )

    with pytest.raises(FerramentaError):
        tool_manager.executar_ferramenta("ferramenta_teste", {})


def test_executar_ferramenta_chama_funcao_registrada(monkeypatch):
    chamadas = {}

    def funcao_falsa(argumentos):
        chamadas["args"] = argumentos
        return {"ok": True}

    monkeypatch.setitem(
        tool_manager.FERRAMENTAS_DISPONIVEIS,
        "ferramenta_teste",
        {
            "descricao": "teste",
            "argumentos_obrigatorios": [],
            "argumentos_opcionais": [],
            "funcao": funcao_falsa,
        },
    )

    resultado = tool_manager.executar_ferramenta(
        "ferramenta_teste",
        {"filiais": ["Timon"]},
    )

    assert resultado == {"ok": True}
    assert chamadas["args"] == {"filiais": ["Timon"]}
