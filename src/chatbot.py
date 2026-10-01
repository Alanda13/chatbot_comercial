"""
Orquestrador principal do Chatbot Comercial.

Este módulo recebe a pergunta do usuário, solicita a interpretação
ao Gemini, executa ferramentas autorizadas e monta a resposta final.
"""
import re

from src.ai_service import interpretar_pergunta
from src.ai_service import gerar_resposta_final
from src.tool_manager import executar_ferramenta
from src.exceptions import FerramentaError, RespostaInvalidaError
from src.logger import obter_logger

logger = obter_logger(__name__)

LIMITE_RESULTADOS_RESPOSTA = 60
LIMITE_MINIMO_PARA_TABELA = 2

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


_NUMERO = re.compile(r"\d+(?:[.,]\d+)*")

_INSTRUCAO_CONSULTAR_DE_NOVO = (
    "\n\n(Instrução do sistema: o valor pedido NÃO aparece no histórico "
    "da conversa. Use a ação \"executar_ferramenta\" para consultá-lo — "
    "não use \"responder_com_historico\".)"
)


def _numeros(texto: str | None) -> set[str]:
    """Números do texto só com os dígitos ("241.509,98" -> "24150998")."""
    return {re.sub(r"[.,]", "", numero) for numero in _NUMERO.findall(texto or "")}


def _numeros_fora_do_historico(
    mensagem: str | None,
    pergunta: str,
    historico: list[dict[str, str]] | None,
) -> set[str]:
    """
    Números da resposta "responder_com_historico" que não aparecem nem
    no histórico nem na pergunta — ou seja, inventados pela IA (ela já
    respondeu "e o percentual?" calculando um % com um faturamento que
    nunca tinha sido mostrado). Números de até 2 dígitos são ignorados
    (numeração de lista, "os 3 maiores").
    """
    permitidos = _numeros(pergunta)

    for mensagem_historico in historico or []:
        permitidos |= _numeros(mensagem_historico.get("conteudo"))

    return {
        numero for numero in _numeros(mensagem)
        if len(numero) > 2 and numero not in permitidos
    }


def processar_pergunta(
    pergunta: str,
    historico: list[dict[str, str]] | None = None,
) -> tuple[str, list[dict] | None, str | None]:
    """
    Executa o fluxo completo do chatbot.

    Retorna uma tupla: (texto_da_resposta, dados_para_tabela,
    nome_ferramenta). dados_para_tabela vem preenchido só quando o
    resultado tiver pelo menos LIMITE_MINIMO_PARA_TABELA linhas —
    usado pelo app.py pra oferecer a visualização em tabela.
    nome_ferramenta identifica qual ferramenta gerou os dados da
    tabela (None quando nenhuma ferramenta foi executada) — o app.py
    usa isso pra saber quais colunas mostrar.
    """

    solicitacao = interpretar_pergunta(
        pergunta=pergunta,
        historico=historico,
    )

    # Trava: "responder_com_historico" só pode reorganizar números que já
    # foram mostrados. Se a resposta trouxer número novo, ela foi
    # inventada — descarta e pede a interpretação de novo, consultando.
    if solicitacao.acao == "responder_com_historico":
        inventados = _numeros_fora_do_historico(
            solicitacao.mensagem, pergunta, historico
        )

        if inventados:
            logger.warning(
                "Resposta pelo histórico descartada — números que não "
                "estão no histórico: %s", sorted(inventados),
            )
            solicitacao = interpretar_pergunta(
                pergunta=pergunta + _INSTRUCAO_CONSULTAR_DE_NOVO,
                historico=historico,
            )

            if solicitacao.acao == "responder_com_historico":
                return (
                    "Não consegui confirmar esse valor com os dados já "
                    "mostrados. Pode refazer a pergunta completa (indicador, "
                    "filial e período)?",
                    None,
                    None,
                )

    if solicitacao.acao == "pedir_esclarecimento":
        return (
            solicitacao.mensagem
            or "Preciso de mais informações para realizar a consulta.",
            None,
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
            None,
        )

    if solicitacao.acao == "responder_com_historico":
        return (
            solicitacao.mensagem
            or "Não consegui reorganizar essa informação. Pode reformular?",
            None,
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

    # "tabela" (linhas já recortadas nas colunas pedidas) é só pra tela;
    # a IA recebe o resultado completo, sem essa cópia.
    resultado_limitado = dict(_limitar_resultados(resultado))
    linhas_tabela = resultado_limitado.pop("tabela", None)

    dados_tabela = None
    lista_resultados = linhas_tabela or resultado_limitado.get("resultados")

    if (
        isinstance(lista_resultados, list)
        and len(lista_resultados) >= LIMITE_MINIMO_PARA_TABELA
    ):
        dados_tabela = lista_resultados[:LIMITE_RESULTADOS_RESPOSTA]

    resposta_final = gerar_resposta_final(
        pergunta=pergunta,
        nome_ferramenta=solicitacao.ferramenta,
        resultado=resultado_limitado,
        historico=historico,
    )

    return (resposta_final, dados_tabela, solicitacao.ferramenta)
    

