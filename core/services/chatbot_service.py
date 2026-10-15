"""
Orquestrador principal do Chatbot Comercial.

Este módulo recebe a pergunta do usuário, solicita a interpretação
ao Gemini, executa ferramentas autorizadas e monta a resposta final.
"""
import re
import time

from core.services.ia_service import interpretar_pergunta
from core.services.ia_service import gerar_resposta_final
from core.services.ferramentas.tool_manager import executar_ferramenta
from core.exceptions import FerramentaError, RespostaInvalidaError
from core.logger import obter_logger
from core.motor import catalogo

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
        criterio = ""
        campo = _campo_pra_cortar(resultado)

        # Sem ordem pedida, a lista vem em ordem alfabética: ordena pelo campo
        # principal antes de cortar.
        if campo:
            ordem = sorted(
                range(len(resultados)),
                key=lambda i: resultados[i].get(campo) or 0, reverse=True,
            )
            resultados = [resultados[i] for i in ordem]
            criterio = f" (os {LIMITE_RESULTADOS_RESPOSTA} maiores em {campo})"
            tabela = resultado.get("tabela")

            # A tabela da tela é a mesma lista (linha a linha), só com as
            # colunas recortadas: mesma ordem, pra mostrar os mesmos itens.
            if isinstance(tabela, list) and len(tabela) == len(ordem):
                resultado["tabela"] = [tabela[i] for i in ordem]

        resultado["resultados"] = resultados[:LIMITE_RESULTADOS_RESPOSTA]
        # O aviso diz a quantidade total, pra IA não responder "60 de N".
        resultado["aviso"] = (
            f"A lista completa tem {len(resultados)} itens; aqui vão só "
            f"{LIMITE_RESULTADOS_RESPOSTA}{criterio}, pra citar exemplos. "
            f"Quando disser QUANTOS são, use {len(resultados)}. Não escreva "
            "\"mostrando 60 de…\": se for útil, diga que a lista completa "
            "está na tabela ou que dá pra filtrar (uma filial, um RCA, um "
            "período menor). Se vier \"total_de_todas_as_linhas\", ele "
            f"é de TODOS os {len(resultados)} itens, não só dos mostrados: "
            "nunca o chame de total \"desse grupo\" ou \"dos N maiores\"."
        )

    return resultado


_DIMENSOES_DE_TEMPO = ("ano", "mes", "dia", "dia_semana", "semana")


def _campo_pra_cortar(resultado: dict) -> str | None:
    """
    Campo pelo qual ordenar antes de cortar a lista: o valor em R$ do
    indicador (campo_variacao, ex: valor do desconto) ou o principal. Não
    reordena lista já ordenada nem lista no tempo (mês a mês fica em ordem).
    """
    if resultado.get("criterio_da_ordem"):
        return None

    if any(dimensao in _DIMENSOES_DE_TEMPO for dimensao in resultado.get("agrupar_por") or []):
        return None

    definicao = catalogo.INDICADORES.get(resultado.get("indicador"), {})
    campo = definicao.get("campo_variacao") or definicao.get("campo_principal")
    linhas = resultado.get("resultados") or []

    return campo if linhas and campo in linhas[0] else None


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


def _registrar_tempos(tempos: dict[str, float]) -> None:
    """Uma linha no log por pergunta: quanto levou cada etapa."""
    logger.info(
        "Tempo | %s | total %.1f s",
        " | ".join(f"{etapa} {segundos:.1f} s" for etapa, segundos in tempos.items()),
        sum(tempos.values()),
    )


def _sem_aviso(etapa: str) -> None:
    pass


def processar_pergunta(
    pergunta: str,
    historico: list[dict[str, str]] | None = None,
    avisar_etapa=_sem_aviso,
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
    avisar_etapa(texto) é chamada no começo de cada etapa (a tela mostra
    "Entendendo a pergunta…", "Buscando os dados…", "Escrevendo…").
    """
    tempos: dict[str, float] = {}
    inicio = time.perf_counter()

    avisar_etapa("Entendendo a pergunta…")
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

    tempos["entender"] = time.perf_counter() - inicio

    if solicitacao.acao != "executar_ferramenta":
        _registrar_tempos(tempos)

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

    avisar_etapa("Buscando os dados…")
    inicio = time.perf_counter()

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

    tempos["calcular"] = time.perf_counter() - inicio
    avisar_etapa("Escrevendo a resposta…")
    inicio = time.perf_counter()

    resposta_final = gerar_resposta_final(
        pergunta=pergunta,
        nome_ferramenta=solicitacao.ferramenta,
        resultado=resultado_limitado,
        historico=historico,
    )

    tempos["escrever"] = time.perf_counter() - inicio
    _registrar_tempos(tempos)

    return (resposta_final, dados_tabela, solicitacao.ferramenta)
    

