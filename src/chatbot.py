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

## função principal que será chamada pelo app.py futuramente! 
def processar_pergunta(
    pergunta: str,
    historico: list[dict[str, str]] | None = None,
) -> str:
    """
    Executa o fluxo completo do chatbot.

    1. Interpreta a pergunta com o Gemini.
    2. Analisa a ação solicitada.
    3. Executa a ferramenta autorizada.
    4. Formata a resposta para o usuário.
    """

    solicitacao = interpretar_pergunta(
        pergunta=pergunta,
        historico=historico,
    )

    if solicitacao.acao == "pedir_esclarecimento":
        return (
            solicitacao.mensagem
            or "Preciso de mais informações para realizar a consulta."
        )

    if solicitacao.acao == "fora_do_escopo":
        return (
            solicitacao.mensagem
            or (
                "Essa pergunta ainda está fora do escopo do chatbot. "
                "Neste momento, estão disponíveis consultas de NPS."
            )
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
        # Erros esperados do domínio (filial não encontrada, período
        # inválido, agrupamento inválido, etc.) não abortam a conversa:
        # viram um resultado "não encontrado" e passam pela mesma etapa
        # de formulação natural da resposta final, em vez de expor o
        # texto cru da exceção ao usuário.
        resultado = {
            "encontrado": False,
            "mensagem": str(error),
        }

    resposta_final = gerar_resposta_final(
        pergunta=pergunta,
        nome_ferramenta=solicitacao.ferramenta,
        resultado=resultado,
    )
    return resposta_final
    

