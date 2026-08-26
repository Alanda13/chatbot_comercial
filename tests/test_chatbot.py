from unittest.mock import patch

import pytest

from src.chatbot import processar_pergunta
from src.exceptions import FerramentaError, RespostaInvalidaError
from src.schemas import SolicitacaoFerramenta


@patch("src.chatbot.gerar_resposta_final", return_value="resposta final")
@patch("src.chatbot.executar_ferramenta", return_value={"faturamento": 100})
@patch("src.chatbot.interpretar_pergunta")
def test_processar_pergunta_executa_ferramenta(
    mock_interpretar,
    mock_executar,
    mock_gerar,
):
    mock_interpretar.return_value = SolicitacaoFerramenta(
        acao="executar_ferramenta",
        ferramenta="consultar_indicadores_faturamento",
        argumentos={"meses": [7], "anos": [2025]},
    )

    resultado = processar_pergunta("Qual o faturamento de julho de 2025?")

    assert resultado == "resposta final"
    mock_executar.assert_called_once_with(
        nome_ferramenta="consultar_indicadores_faturamento",
        argumentos={"meses": [7], "anos": [2025]},
    )
    mock_gerar.assert_called_once()


@patch("src.chatbot.interpretar_pergunta")
def test_processar_pergunta_pede_esclarecimento(mock_interpretar):
    mock_interpretar.return_value = SolicitacaoFerramenta(
        acao="pedir_esclarecimento",
        mensagem="Qual período você deseja consultar?",
    )

    resultado = processar_pergunta("Qual o faturamento?")

    assert resultado == "Qual período você deseja consultar?"


@patch("src.chatbot.interpretar_pergunta")
def test_processar_pergunta_fora_do_escopo(mock_interpretar):
    mock_interpretar.return_value = SolicitacaoFerramenta(
        acao="fora_do_escopo",
        mensagem=None,
    )

    resultado = processar_pergunta("Qual é a previsão do tempo?")

    assert "fora do escopo" in resultado.lower()


@patch("src.chatbot.interpretar_pergunta")
def test_processar_pergunta_sem_ferramenta_gera_erro(mock_interpretar):
    mock_interpretar.return_value = SolicitacaoFerramenta(
        acao="executar_ferramenta",
        ferramenta=None,
    )

    with pytest.raises(RespostaInvalidaError):
        processar_pergunta("Qual o faturamento?")


@patch("src.chatbot.gerar_resposta_final", return_value="resposta final")
@patch("src.chatbot.executar_ferramenta")
@patch("src.chatbot.interpretar_pergunta")
def test_processar_pergunta_erro_de_ferramenta_nao_aborta_conversa(
    mock_interpretar,
    mock_executar,
    mock_gerar,
):
    mock_interpretar.return_value = SolicitacaoFerramenta(
        acao="executar_ferramenta",
        ferramenta="consultar_indicadores_nps",
        argumentos={"filiais": ["Marrocos"]},
    )
    mock_executar.side_effect = ValueError(
        "A filial 'Marrocos' não foi encontrada."
    )

    resultado = processar_pergunta("Qual o NPS da filial Marrocos?")

    assert resultado == "resposta final"
    resultado_passado = mock_gerar.call_args.kwargs["resultado"]
    assert resultado_passado["encontrado"] is False
    assert "Marrocos" in resultado_passado["mensagem"]


@patch("src.chatbot.gerar_resposta_final", return_value="resposta final")
@patch("src.chatbot.executar_ferramenta")
@patch("src.chatbot.interpretar_pergunta")
def test_processar_pergunta_erro_de_argumento_obrigatorio_nao_aborta(
    mock_interpretar,
    mock_executar,
    mock_gerar,
):
    mock_interpretar.return_value = SolicitacaoFerramenta(
        acao="executar_ferramenta",
        ferramenta="consultar_indicadores_faturamento_diario",
        argumentos={},
    )
    mock_executar.side_effect = FerramentaError(
        "Argumentos obrigatórios ausentes: periodos"
    )

    resultado = processar_pergunta("Qual o faturamento de hoje?")

    assert resultado == "resposta final"
    resultado_passado = mock_gerar.call_args.kwargs["resultado"]
    assert resultado_passado["encontrado"] is False
