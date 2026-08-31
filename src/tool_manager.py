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
    executar_verificar_rca,
)
from src.faturamento_diario_tools import (
    executar_consulta_indicadores_faturamento_diario,
)
from src.filiais_tools import executar_listar_filiais
from src.exceptions import FerramentaError

FERRAMENTAS_DISPONIVEIS = {
    "listar_filiais": {
        "descricao": (
            "Ferramenta para listar todas as filiais existentes na "
            "base comercial, ou informar a quantidade total de "
            "filiais. Use esta ferramenta sempre que o usuário "
            "perguntar quais filiais existem, quantas filiais tem, "
            "pedir a lista de filiais/lojas/unidades, ou perguntar se "
            "uma filial específica existe na base."
        ),
        "argumentos_obrigatorios": [],
        "argumentos_opcionais": [],
        "funcao": executar_listar_filiais,
    },

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
            "Ferramenta genérica para consultar indicadores de faturamento "
            "por mês e/ou ano (rotina 8280). "
            "Pode consultar a empresa inteira, uma ou várias filiais, "
            "um ou vários RCAs, meses e anos. "
            "Use esta ferramenta para consultas de faturamento, venda bruta, "
            "valor de desconto, peso líquido/toneladas e quantidade de "
            "notas, sempre que a pergunta for por mês(es) e/ou ano(s) — nunca por "
            "um dia específico ou período de dias. "
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

    "verificar_rca": {
        "descricao": (
            "Ferramenta para confirmar se um RCA (vendedor) existe, "
            "por nome ou código, SEM precisar de período. Use esta "
            "ferramenta quando o usuário mencionar um RCA (nome ou "
            "código) em uma pergunta de faturamento mas ainda não "
            "tiver informado o período — assim é possível confirmar "
            "que o RCA existe e avisar direto caso não exista, antes "
            "de pedir o período ao usuário."
        ),
        "argumentos_obrigatorios": ["rca"],
        "argumentos_opcionais": ["filiais"],
        "funcao": executar_verificar_rca,
    },

    "consultar_indicadores_faturamento_diario": {
        "descricao": (
            "Ferramenta para consultar indicadores de faturamento com "
            "granularidade diária (rotina 8302). "
            "Use esta ferramenta sempre que o usuário pedir o faturamento "
            "de um dia específico ou de um período de dias — por exemplo: "
            "hoje, ontem, esta semana, semana passada, ou um intervalo de "
            "datas. Também é a ferramenta correta para faturamento "
            "agrupado por forma de pagamento. "
            "Para perguntas por mês(es) ou ano(s) inteiros, sem exigir "
            "detalhamento por dia, use a ferramenta "
            "'consultar_indicadores_faturamento' no lugar desta."
        ),
        "argumentos_obrigatorios": ["periodos"],
        "argumentos_opcionais": [
            "filiais",
            "rcas",
            "agrupar_por",
        ],
        "funcao": executar_consulta_indicadores_faturamento_diario,
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
        raise FerramentaError(
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
        raise FerramentaError(
            "Argumentos obrigatórios ausentes: "
            + ", ".join(argumentos_faltantes)
        )

    funcao = ferramenta["funcao"]

    return funcao(argumentos)





