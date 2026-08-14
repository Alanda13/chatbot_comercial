"""
Catálogo e gerenciador das ferramentas disponíveis
para o Chatbot Comercial.

Este arquivo registra as ferramentas autorizadas,
seus argumentos obrigatórios e as funções Python
que devem ser executadas.
"""

from src.nps_tools import executar_consulta_indicadores_nps
from src.faturamento_tools import (
    executar_consulta_indicadores_faturamento,
)

FERRAMENTAS_DISPONIVEIS = {
    "consultar_indicadores_nps": {
        "descricao": (
            "Ferramenta genérica para consultar indicadores de NPS. "
            "Pode consultar a empresa inteira, uma filial específica ou várias filiais, "
            "com nenhum, um ou vários períodos. "
            "Use esta ferramenta para consultas de NPS, quantidade de respostas, "
            "promotores, neutros, detratores e comparações entre filiais. "
            "Quando a consulta for da empresa inteira, não envie filiais."
        ),
        "argumentos_obrigatorios": [],
        "argumentos_opcionais": [
            "filiais",
            "periodos",
        ],
        "funcao": executar_consulta_indicadores_nps,
    },

    "consultar_indicadores_faturamento": {
        "descricao": (
            "Ferramenta genérica para consultar indicadores de faturamento. "
            "Pode consultar a empresa inteira, uma ou várias filiais, "
            "um ou vários RCAs, meses e anos. "
            "Use esta ferramenta para consultas de faturamento, venda bruta, "
            "valor de desconto, peso líquido e quantidade de notas. "
            "O faturamento é baseado na coluna VENDA_LIQ da rotina 8280."
        ),
        "argumentos_obrigatorios": [],
        "argumentos_opcionais": [
            "filiais",
            "rcas",
            "meses",
            "anos",
            "agrupar_por",
        ],
        "funcao": executar_consulta_indicadores_faturamento,
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
        argumentos_opcionais = dados.get("argumentos_opcionais", [])   

        if argumentos:
            texto_argumentos = ", ".join(argumentos)
        else:
            texto_argumentos = "nenhum"

        if argumentos_opcionais:
            texto_opcionais = ", ".join(
                argumentos_opcionais
                )
        else:
            texto_opcionais = "nenhum"
   
        linhas.append(
            f"- {nome}\n"
            f"  Descrição: {descricao}\n"
            f"  Argumentos obrigatórios: {texto_argumentos}\n"
            f"  Argumentos_opcionais: {texto_opcionais}"
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





