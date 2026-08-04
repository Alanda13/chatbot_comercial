"""
Orquestrador principal do Chatbot Comercial.

Este módulo recebe a pergunta do usuário, solicita a interpretação
ao Gemini, executa ferramentas autorizadas e monta a resposta final.
"""
from typing import Any

from src.ai_service import interpretar_pergunta
from src.tool_manager import executar_ferramenta

# função que vai converter os valores para o padrão brasileiro.
def formatar_numero(valor: int | float) -> str:
    """
    Formata números no padrão brasileiro.

    Exemplos:
        82027 -> 82.027
        87.27 -> 87,27
    """

    if isinstance(valor, int):
        return f"{valor:,}".replace(",", ".")

    return (
        f"{valor:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )

# essa função analisa qual ferramenta foi executada e cria a mensagem correspondente.  
def formatar_resultado(
    nome_ferramenta: str,
    resultado: dict[str, Any],
) -> str:
    """
    Transforma o resultado da ferramenta em uma resposta
    compreensível para o usuário.
    """

    if nome_ferramenta == "consultar_nps_geral":
        return (
            f"O NPS geral da empresa é "
            f"**{formatar_numero(resultado['nps_geral'])}**, "
            f"calculado com base em "
            f"**{formatar_numero(resultado['total_respostas'])} respostas**.\n\n"
            f"Promotores: "
            f"**{formatar_numero(resultado['percentual_promotores'])}%**  \n"
            f"Neutros: "
            f"**{formatar_numero(resultado['percentual_neutros'])}%**  \n"
            f"Detratores: "
            f"**{formatar_numero(resultado['percentual_detratores'])}%**"
        )

    if nome_ferramenta == "consultar_nps_por_filial":
        return (
            f"O NPS da filial **{resultado['filial']}** é "
            f"**{formatar_numero(resultado['nps'])}**, "
            f"calculado com base em "
            f"**{formatar_numero(resultado['total_respostas'])} respostas**."
        )

    if nome_ferramenta == "consultar_nps_por_periodo":
        if resultado["nps"] is None:
            return (
                "Não foram encontradas avaliações válidas "
                "no período informado."
            )

        return (
            f"O NPS entre **{resultado['data_inicial']}** e "
            f"**{resultado['data_final']}** foi "
            f"**{formatar_numero(resultado['nps'])}**, "
            f"com base em "
            f"**{formatar_numero(resultado['total_respostas'])} respostas**."
        )

    if nome_ferramenta == "comparar_nps_periodos":
        atual = resultado["periodo_atual"]
        anterior = resultado["periodo_anterior"]

        if resultado["variacao"] is None:
            return resultado["situacao"]

        return (
            f"No período atual, o NPS foi "
            f"**{formatar_numero(atual['nps'])}**. "
            f"No período anterior, foi "
            f"**{formatar_numero(anterior['nps'])}**.\n\n"
            f"A variação foi de "
            f"**{formatar_numero(resultado['variacao'])} ponto(s)**. "
            f"{resultado['situacao']}."
        )

    raise ValueError(
        f"Não existe formatação para a ferramenta '{nome_ferramenta}'."
    )

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
        raise ValueError(
            f"Ação não reconhecida: {solicitacao.acao}"
        )

    if not solicitacao.ferramenta:
        raise ValueError(
            "A IA solicitou uma execução, mas não informou a ferramenta."
        )

    resultado = executar_ferramenta(
        nome_ferramenta=solicitacao.ferramenta,
        argumentos=solicitacao.argumentos,
    )

    return formatar_resultado(
        nome_ferramenta=solicitacao.ferramenta,
        resultado=resultado,
    )