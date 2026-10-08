import pytest

from core.services.ferramentas import tool_manager
from core.exceptions import FerramentaError


def test_ferramenta_existe():
    assert tool_manager.ferramenta_existe("listar_filiais") is True
    assert (
        tool_manager.ferramenta_existe("consultar_dados_comerciais") is True
    )
    assert tool_manager.ferramenta_existe("verificar_rca") is True
    # Substituídas por "consultar_dados_comerciais" — não são mais
    # registradas como ferramenta própria (veja core/motor/orquestrador.py).
    assert (
        tool_manager.ferramenta_existe("consultar_indicadores_faturamento")
        is False
    )
    assert (
        tool_manager.ferramenta_existe(
            "consultar_indicadores_faturamento_diario"
        )
        is False
    )
    assert tool_manager.ferramenta_existe("consultar_metas") is False
    assert tool_manager.ferramenta_existe("consultar_meta_tonelada") is False
    assert (
        tool_manager.ferramenta_existe("consultar_crescimento_abaixo_meta")
        is False
    )
    assert tool_manager.ferramenta_existe("listar_rcas_filial") is False
    assert tool_manager.ferramenta_existe("consultar_indicadores_nps") is False
    assert tool_manager.ferramenta_existe("consultar_evolucao_nps") is False
    assert tool_manager.ferramenta_existe("nao_existe") is False


def test_consultar_dados_comerciais_exige_indicador_como_obrigatorio():
    argumentos = tool_manager.obter_argumentos_obrigatorios(
        "consultar_dados_comerciais"
    )
    assert argumentos == ["indicador"]


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
