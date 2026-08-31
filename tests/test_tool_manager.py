import pytest

from src import tool_manager
from src.exceptions import FerramentaError


def test_ferramenta_existe():
    assert tool_manager.ferramenta_existe("listar_filiais") is True
    assert tool_manager.ferramenta_existe("consultar_indicadores_nps") is True
    assert (
        tool_manager.ferramenta_existe("consultar_indicadores_faturamento")
        is True
    )
    assert (
        tool_manager.ferramenta_existe(
            "consultar_indicadores_faturamento_diario"
        )
        is True
    )
    assert tool_manager.ferramenta_existe("verificar_rca") is True
    assert tool_manager.ferramenta_existe("nao_existe") is False


def test_faturamento_diario_exige_periodo_como_obrigatorio():
    argumentos = tool_manager.obter_argumentos_obrigatorios(
        "consultar_indicadores_faturamento_diario"
    )
    assert argumentos == ["periodos"]


def test_verificar_rca_exige_rca_como_obrigatorio_e_nao_exige_periodo():
    argumentos = tool_manager.obter_argumentos_obrigatorios(
        "verificar_rca"
    )
    assert argumentos == ["rca"]


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
