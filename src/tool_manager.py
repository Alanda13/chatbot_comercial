"""
Catálogo e gerenciador das ferramentas disponíveis
para o Chatbot Comercial.

Este arquivo registra as ferramentas autorizadas,
seus argumentos obrigatórios e as funções Python
que devem ser executadas.
"""

from src.nps_tools import (
    executar_comparacao_nps,
    executar_nps_geral,
    executar_nps_por_filial,
    executar_nps_por_periodo,
)


FERRAMENTAS_DISPONIVEIS = {
    "consultar_nps_geral": {
        "descricao": (
            "Consulta o NPS geral da empresa, incluindo "
            "quantidade de respostas e percentuais de "
            "promotores, neutros e detratores."
        ),
        "argumentos_obrigatorios": [],
        "funcao": executar_nps_geral,
    },

    "consultar_nps_por_filial": {
        "descricao": (
            "Consulta o NPS de uma loja ou filial específica."
        ),
        "argumentos_obrigatorios": [
            "filial",
        ],
        "funcao": executar_nps_por_filial,
    },

    "consultar_nps_por_periodo": {
        "descricao": (
            "Consulta o NPS da empresa dentro de um "
            "intervalo de datas."
        ),
        "argumentos_obrigatorios": [
            "data_inicial",
            "data_final",
        ],
        "funcao": executar_nps_por_periodo,
    },

    "comparar_nps_periodos": {
        "descricao": (
            "Compara o NPS de dois períodos e informa "
            "a variação entre os resultados."
        ),
        "argumentos_obrigatorios": [
            "data_inicial_atual",
            "data_final_atual",
            "data_inicial_anterior",
            "data_final_anterior",
        ],
        "funcao": executar_comparacao_nps,
    },
}


def gerar_catalogo_ferramentas() -> str:
    """
    Gera o texto com as ferramentas disponíveis.

    Esse texto será enviado ao Gemini junto com o prompt.
    A função Python interna não é enviada à IA.
    """

    linhas = []

    for nome, dados in FERRAMENTAS_DISPONIVEIS.items():
        descricao = dados["descricao"]
        argumentos = dados["argumentos_obrigatorios"]

        if argumentos:
            texto_argumentos = ", ".join(argumentos)
        else:
            texto_argumentos = "nenhum"

        linhas.append(
            f"- {nome}\n"
            f"  Descrição: {descricao}\n"
            f"  Argumentos obrigatórios: {texto_argumentos}"
        )

    return "\n\n".join(linhas)


def ferramenta_existe(nome_ferramenta: str) -> bool:
    """
    Verifica se uma ferramenta está cadastrada
    e autorizada pelo sistema.
    """

    return nome_ferramenta in FERRAMENTAS_DISPONIVEIS


def obter_argumentos_obrigatorios(
    nome_ferramenta: str,
) -> list[str]:
    """
    Retorna os argumentos obrigatórios de uma ferramenta.

    Caso a ferramenta não exista, retorna uma lista vazia.
    """

    ferramenta = FERRAMENTAS_DISPONIVEIS.get(nome_ferramenta)

    if ferramenta is None:
        return []

    return ferramenta["argumentos_obrigatorios"]


def executar_ferramenta(
    nome_ferramenta: str,
    argumentos: dict,
) -> dict:
    """
    Valida e executa uma ferramenta cadastrada.

    O sistema verifica:
    1. se a ferramenta existe;
    2. se os argumentos obrigatórios foram enviados;
    3. qual função Python deve ser executada.
    """

    ferramenta = FERRAMENTAS_DISPONIVEIS.get(
        nome_ferramenta
    )

    if ferramenta is None:
        raise ValueError(
            f"A ferramenta '{nome_ferramenta}' não existe."
        )

    argumentos_obrigatorios = ferramenta[
        "argumentos_obrigatorios"
    ]

    argumentos_faltantes = [
        argumento
        for argumento in argumentos_obrigatorios
        if not argumentos.get(argumento)
    ]

    if argumentos_faltantes:
        raise ValueError(
            "Argumentos obrigatórios ausentes: "
            + ", ".join(argumentos_faltantes)
        )

    funcao = ferramenta["funcao"]

    return funcao(argumentos)