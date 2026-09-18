"""
Catálogo e gerenciador das ferramentas disponíveis
para o Chatbot Comercial.

Este arquivo registra as ferramentas autorizadas,
seus argumentos obrigatórios e as funções Python
que devem ser executadas.
"""

from src.nps_tools import (
    executar_consulta_indicadores_nps,
    executar_consultar_evolucao_nps,
)
from src.faturamento_tools import executar_verificar_rca
from src.filiais_tools import executar_listar_filiais
from src.indicador_tools import executar_consultar_dados_comerciais
from src.catalogo import gerar_descricao_indicadores
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
            "Quando a consulta for da empresa inteira, não envie filiais. "
            "Para perguntas do tipo 'qual filial teve o maior/menor NPS', "
            "use 'agrupar_por_filial': true em vez de listar filiais uma "
            "a uma — isso traz o NPS de TODAS as filiais de uma vez. "
            "Para perguntas do tipo 'qual ano teve o maior/menor NPS' de "
            "uma filial (ou da empresa), use 'agrupar_por_ano': true em "
            "vez de listar anos um a um — o sistema descobre sozinho "
            "quais anos têm dado. "
            "Para perguntas do tipo 'NPS mês a mês', 'liste os meses' ou "
            "quando o usuário nomear vários meses de um ou mais anos "
            "(inclusive para COMPARAR meses entre anos diferentes, como "
            "'compare o NPS de cada mês em 2024 e 2025'), use "
            "'agrupar_por_mes': true junto com 'anos' (uma LISTA com "
            "um ou mais anos, ex: [2024, 2025]) em vez de montar os "
            "períodos de cada mês manualmente. "
            "NÃO use esta ferramenta para 'qual filial teve a maior "
            "evolução/queda de NPS entre dois anos' — use "
            "'consultar_evolucao_nps' para isso."
        ),
        "argumentos_obrigatorios": [],
        "argumentos_opcionais": [
            "filiais",
            "periodos",
            "agrupar_por_filial",
            "agrupar_por_ano",
            "agrupar_por_mes",
            "anos",
        ],
        "funcao": executar_consulta_indicadores_nps,
    },

    "consultar_evolucao_nps": {
        "descricao": (
            "Ferramenta para identificar qual filial teve a maior "
            "evolução (melhora) ou queda de NPS entre dois anos. Use "
            "para perguntas do tipo 'qual filial teve a maior "
            "evolução de NPS entre 2024 e 2025', 'que filial mais "
            "melhorou o NPS'. O cálculo da diferença entre os dois "
            "anos, para cada filial, é feito de forma exata pelo "
            "sistema (já vem ordenado da maior evolução pra maior "
            "queda) — não pela IA. Se o usuário não informar filiais "
            "específicas, não envie o argumento 'filiais' (traz "
            "todas)."
        ),
        "argumentos_obrigatorios": ["ano_inicial", "ano_final"],
        "argumentos_opcionais": ["filiais"],
        "funcao": executar_consultar_evolucao_nps,
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

    "consultar_dados_comerciais": {
        "descricao": (
            "Ferramenta GENÉRICA de consulta a indicadores comerciais — "
            "prefira esta ferramenta em vez das ferramentas específicas "
            "acima quando o indicador pedido estiver na lista abaixo. "
            "Recebe: 'indicador' (obrigatório, um dos listados abaixo); "
            "'periodo' (um de: hoje, ontem, semana_atual, mes_atual, "
            "ano_atual, mes_anterior, mesmo_mes_ano_anterior, "
            "personalizado); 'periodo_personalizado' (obrigatório só "
            "quando periodo='personalizado' — {\"meses\": [...], "
            "\"anos\": [...]} para indicadores de período mensal, ou "
            "{\"data_inicial\": \"AAAA-MM-DD\", \"data_final\": "
            "\"AAAA-MM-DD\"} para indicadores de período diário); "
            "'filtros' ({dimensao: valor(es)}, ex: {\"filial\": "
            "[\"Timon\"]}); 'agrupar_por' (lista de dimensões, ex: "
            "[\"filial\", \"mes\"]); 'comparar_com' (outro período, "
            "pra calcular crescimento em relação a ele — o resultado "
            "já vem com a diferença e o percentual calculados, NÃO "
            "calcule você mesma(o)); 'filtros_calculados' (filtro "
            "sobre a métrica já calculada, ex: [{\"campo\": "
            "\"percentual_atingimento\", \"operador\": \">=\", "
            "\"valor\": 100}] pra 'quem bateu a meta' — o filtro é "
            "exato, aplicado pelo sistema); 'ordenar_por' "
            "({\"campo\": ..., \"ordem\": \"desc\"|\"asc\" (padrão "
            "\"desc\"), \"limite\": N}) — use SEMPRE que a pergunta "
            "pedir 'o maior/menor', 'quem mais/menos', ou 'os N "
            "maiores/menores' de um grupo (ex: \"agrupar_por\": "
            "[\"filial\"] junto com \"ordenar_por\": {\"campo\": "
            "\"faturamento\", \"limite\": 1} pra 'qual filial teve o "
            "maior faturamento'). O sistema ordena e corta de forma "
            "EXATA — NUNCA tente identificar o maior/menor você "
            "mesma(o) olhando uma lista grande de resultados, "
            "PEÇA pro sistema já ordenado e cortado. "
            "Indicadores disponíveis nesta ferramenta:\n"
            f"{gerar_descricao_indicadores()}\n"
            "Para indicadores que NÃO estão nessa lista (nps e "
            "qualquer outro), use a ferramenta "
            "específica correspondente, não esta."
        ),
        "argumentos_obrigatorios": ["indicador"],
        "argumentos_opcionais": [
            "periodo",
            "periodo_personalizado",
            "filtros",
            "agrupar_por",
            "comparar_com",
            "filtros_calculados",
            "ordenar_por",
        ],
        "funcao": executar_consultar_dados_comerciais,
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