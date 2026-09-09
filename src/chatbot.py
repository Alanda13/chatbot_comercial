"""
Orquestrador principal do Chatbot Comercial.

Este módulo recebe a pergunta do usuário, solicita a interpretação
ao Gemini, executa ferramentas autorizadas e monta a resposta final.
"""
from src.ai_service import interpretar_pergunta
from src.ai_service import gerar_resposta_final
from src.tool_manager import executar_ferramenta
from src.exceptions import FerramentaError, RespostaInvalidaError
from src.logger import obter_logger

logger = obter_logger(__name__)

LIMITE_RESULTADOS_RESPOSTA = 60
LIMITE_MINIMO_PARA_TABELA = 3

def _limitar_resultados(resultado: dict) -> dict:
    """
    Evita mandar uma quantidade enorme de linhas de uma vez pra IA
    formular a resposta final (ex: todos os RCAs vezes todos os dias
    de um mês) — isso estoura o limite do modelo e falha. Trunca e
    avisa, em vez de tentar processar tudo de uma vez.
    """
    resultados = resultado.get("resultados")

    if (
        isinstance(resultados, list)
        and len(resultados) > LIMITE_RESULTADOS_RESPOSTA
    ):
        resultado = dict(resultado)
        resultado["resultados"] = resultados[:LIMITE_RESULTADOS_RESPOSTA]
        resultado["aviso"] = (
            f"Mostrando {LIMITE_RESULTADOS_RESPOSTA} de "
            f"{len(resultados)} resultados. Peça um filtro mais "
            "específico (uma filial, um RCA, ou um período menor) "
            "para ver o restante."
        )

    return resultado

def processar_pergunta(
    pergunta: str,
    historico: list[dict[str, str]] | None = None,
) -> tuple[str, list[dict] | None]:
    """
    Executa o fluxo completo do chatbot.

    Retorna uma tupla: (texto_da_resposta, dados_para_tabela).
    dados_para_tabela vem preenchido só quando o resultado tiver mais
    de LIMITE_MINIMO_PARA_TABELA linhas — usado pelo app.py pra
    oferecer a visualização em tabela.
    """

    solicitacao = interpretar_pergunta(
        pergunta=pergunta,
        historico=historico,
    )

    if solicitacao.acao == "pedir_esclarecimento":
        return (
            solicitacao.mensagem
            or "Preciso de mais informações para realizar a consulta.",
            None,
        )

    if solicitacao.acao == "fora_do_escopo":
        return (
            solicitacao.mensagem
            or (
                "Essa pergunta ainda está fora do escopo do chatbot. "
                "Neste momento, estão disponíveis consultas de NPS."
            ),
            None,
        )

    if solicitacao.acao == "responder_com_historico":
        return (
            solicitacao.mensagem
            or "Não consegui reorganizar essa informação. Pode reformular?",
            None,
        )

    if solicitacao.acao != "executar_ferramenta":
        raise RespostaInvalidaError(
            f"Ação não reconhecida: {solicitacao.acao}"
        )

    if not solicitacao.ferramenta:
        raise RespostaInvalidaError(
            "A IA solicitou uma execução, mas não informou a ferramenta."
        )

    logger.info(
        "Ferramenta escolhida: %s | argumentos: %s",
        solicitacao.ferramenta,
        solicitacao.argumentos,
    )

    try:
        resultado = executar_ferramenta(
            nome_ferramenta=solicitacao.ferramenta,
            argumentos=solicitacao.argumentos,
        )
        logger.info("Resultado da ferramenta: %s", resultado)
    except (FerramentaError, ValueError) as error:
        resultado = {
            "encontrado": False,
            "mensagem": str(error),
        }

    resultado_limitado = _limitar_resultados(resultado)

    dados_tabela = None
    lista_resultados = resultado_limitado.get("resultados")

    if (
        isinstance(lista_resultados, list)
        and len(lista_resultados) > LIMITE_MINIMO_PARA_TABELA
    ):
        dados_tabela = lista_resultados

    resposta_final = gerar_resposta_final(
        pergunta=pergunta,
        nome_ferramenta=solicitacao.ferramenta,
        resultado=resultado_limitado,
        historico=historico,
    )

    return (resposta_final, dados_tabela)
    

