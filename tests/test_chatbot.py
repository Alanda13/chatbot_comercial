from unittest.mock import patch

import pytest

from src.chatbot import _limitar_resultados, processar_pergunta
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

    historico = [
        {"papel": "user", "conteudo": "Quantas toneladas em abril?"},
        {"papel": "assistant", "conteudo": "688,18 toneladas."},
    ]

    resultado = processar_pergunta(
        "Qual o faturamento de julho de 2025?",
        historico=historico,
    )

    assert resultado == "resposta final"
    mock_executar.assert_called_once_with(
        nome_ferramenta="consultar_indicadores_faturamento",
        argumentos={"meses": [7], "anos": [2025]},
    )
    mock_gerar.assert_called_once()
    assert mock_gerar.call_args.kwargs["historico"] == historico


@patch("src.chatbot.interpretar_pergunta")
def test_processar_pergunta_pede_esclarecimento(mock_interpretar):
    mock_interpretar.return_value = SolicitacaoFerramenta(
        acao="pedir_esclarecimento",
        mensagem="Qual período você deseja consultar?",
    )

    resultado = processar_pergunta("Qual o faturamento?")

    assert resultado == "Qual período você deseja consultar?"


@patch("src.chatbot.interpretar_pergunta")
def test_processar_pergunta_responder_com_historico(mock_interpretar):
    mock_interpretar.return_value = SolicitacaoFerramenta(
        acao="responder_com_historico",
        mensagem="Do maior para o menor: Maiobão, Timon, Tibiri.",
    )

    resultado = processar_pergunta("Organize do maior para o menor.")

    assert resultado == "Do maior para o menor: Maiobão, Timon, Tibiri."


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


def test_limitar_resultados_nao_mexe_em_lista_pequena():
    resultado = {"resultados": [{"rca": 1}, {"rca": 2}]}

    assert _limitar_resultados(resultado) == resultado


def test_limitar_resultados_trunca_lista_grande():
    resultados_originais = [{"rca": indice} for indice in range(200)]
    resultado = {"resultados": resultados_originais}

    resultado_limitado = _limitar_resultados(resultado)

    assert len(resultado_limitado["resultados"]) == 60
    assert "aviso" in resultado_limitado
    assert "200" in resultado_limitado["aviso"]


@patch("src.chatbot.gerar_resposta_final", return_value="resposta final")
@patch("src.chatbot.executar_ferramenta")
@patch("src.chatbot.interpretar_pergunta")
def test_processar_pergunta_limita_resultado_grande_antes_de_gerar_resposta(
    mock_interpretar,
    mock_executar,
    mock_gerar,
):
    mock_interpretar.return_value = SolicitacaoFerramenta(
        acao="executar_ferramenta",
        ferramenta="consultar_indicadores_faturamento_diario",
        argumentos={
            "periodos": [
                {"data_inicial": "2025-09-01", "data_final": "2025-09-30"}
            ],
            "agrupar_por": ["rca", "dia"],
        },
    )
    mock_executar.return_value = {
        "encontrado": True,
        "resultados": [{"rca": indice} for indice in range(500)],
    }

    processar_pergunta("Liste os RCAs e seus faturamentos todos os dias.")

    resultado_passado = mock_gerar.call_args.kwargs["resultado"]
    assert len(resultado_passado["resultados"]) == 60


# --- trava contra números inventados no "responder_com_historico" ---

HISTORICO_DESCONTO = [
    {"papel": "user", "conteudo": "Qual o desconto de Parnaíba no mês passado?"},
    {
        "papel": "assistant",
        "conteudo": (
            "O desconto concedido pela filial Parnaíba no mês passado "
            "(setembro de 2026) foi de R$ 241.509,98."
        ),
    },
]


@patch("src.chatbot.interpretar_pergunta")
def test_responder_com_historico_so_com_numeros_ja_mostrados_e_aceito(
    mock_interpretar,
):
    mock_interpretar.return_value = SolicitacaoFerramenta(
        acao="responder_com_historico",
        mensagem="Em setembro de 2026, Parnaíba concedeu R$ 241.509,98 de desconto.",
    )

    resposta, _, _ = processar_pergunta("repete o valor", historico=HISTORICO_DESCONTO)

    assert "241.509,98" in resposta
    assert mock_interpretar.call_count == 1


@patch("src.chatbot.gerar_resposta_final", return_value="O percentual foi de 6,86%.")
@patch("src.chatbot.executar_ferramenta", return_value={"encontrado": True, "resultados": []})
@patch("src.chatbot.interpretar_pergunta")
def test_responder_com_historico_com_numero_inventado_consulta_de_novo(
    mock_interpretar, mock_executar, mock_gerar,
):
    mock_interpretar.side_effect = [
        # 1ª interpretação: inventa um % com um faturamento nunca mostrado
        SolicitacaoFerramenta(
            acao="responder_com_historico",
            mensagem=(
                "O percentual foi de 2,21% (R$ 241.509,98 sobre "
                "R$ 10.925.753,74)."
            ),
        ),
        # 2ª interpretação (com a instrução de consultar): consulta
        SolicitacaoFerramenta(
            acao="executar_ferramenta",
            ferramenta="consultar_dados_comerciais",
            argumentos={"indicador": "desconto", "periodo": "mes_anterior"},
        ),
    ]

    resposta, _, _ = processar_pergunta(
        "e o percentual de desconto", historico=HISTORICO_DESCONTO
    )

    assert resposta == "O percentual foi de 6,86%."
    assert mock_interpretar.call_count == 2
    mock_executar.assert_called_once()
    # a resposta final é gerada com a pergunta ORIGINAL, sem a instrução
    assert mock_gerar.call_args.kwargs["pergunta"] == "e o percentual de desconto"


@patch("src.chatbot.interpretar_pergunta")
def test_responder_com_historico_insistindo_em_inventar_nao_mostra_o_numero(
    mock_interpretar,
):
    mock_interpretar.return_value = SolicitacaoFerramenta(
        acao="responder_com_historico",
        mensagem="O percentual foi de 8,42%.",
    )

    resposta, _, _ = processar_pergunta(
        "e o percentual de desconto", historico=HISTORICO_DESCONTO
    )

    assert "8,42" not in resposta
    assert "refazer a pergunta" in resposta
