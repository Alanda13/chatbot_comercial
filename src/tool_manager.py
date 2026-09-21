"""
Catálogo e gerenciador das ferramentas disponíveis
para o Chatbot Comercial.

Este arquivo registra as ferramentas autorizadas,
seus argumentos obrigatórios e as funções Python
que devem ser executadas.
"""

from src.faturamento_tools import executar_verificar_rca
from src.filiais_tools import executar_listar_filiais
from src.indicador_tools import executar_consultar_dados_comerciais
from src.catalogo import gerar_descricao_cruzamentos, gerar_descricao_indicadores
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
            "calcule você mesma(o)); 'comparar_com_personalizado' "
            "(mesmo formato de 'periodo_personalizado', obrigatório só "
            "quando comparar_com='personalizado' — pra comparar com "
            "um período qualquer, ex: {\"anos\": [2023]}). ATENÇÃO: "
            "pra comparar o MESMO intervalo em outro ano (ex: 1º semestre "
            "de 2025 x 1º semestre de 2024) REPITA os meses, "
            "{\"meses\": [1, 2, 3, 4, 5, 6], \"anos\": [2024]} — se "
            "omitir 'meses', compara com o ANO INTEIRO; "
            "'filtros_calculados' (filtro "
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
            "'comparar_filtros' ({dimensao: valor}) — use quando o "
            "usuário pedir para COMPARAR DOIS ITENS da mesma dimensão "
            "entre si (duas filiais, dois estados, dois RCAs), ex: "
            "'compare o NPS de Lourival e Santa Inês mês a mês' = "
            "{\"indicador\": \"nps\", \"filtros\": {\"filial\": "
            "[\"Lourival\"], \"ano\": [2025]}, \"comparar_filtros\": "
            "{\"filial\": [\"Santa Inês\"]}, \"agrupar_por\": "
            "[\"mes\"]}. O 1º item citado vai em 'filtros', o 2º em "
            "'comparar_filtros', e a dimensão comparada NÃO entra em "
            "'agrupar_por'. O resultado já traz o valor de cada um, a "
            "diferença (1º menos 2º) e o percentual — NÃO calcule você "
            "mesma(o). Isso é comparar os itens ENTRE SI; NÃO use "
            "'agrupar_por' pela dimensão nesse caso. Para 3 ou mais "
            "itens, use 'agrupar_por'. Se a pergunta compara PERÍODOS "
            "(ex: 2025 contra 2024) de uma ou mais filiais, NÃO use "
            "'comparar_filtros': use 'comparar_com' (e 'agrupar_por': "
            "['filial'] quando forem várias filiais). "
            "'colunas' (lista dos campos que a TABELA da tela deve "
            "mostrar — SOMENTE o que a pergunta pediu, com os nomes dos "
            "campos dos indicadores, ex: 'mostre o NPS e o atingimento da "
            "meta' = [\"nps\", \"percentual_atingimento\"]; a comparação "
            "(anterior, diferença e variação) vem junto sozinha quando "
            "houver 'comparar_com'; sem 'colunas' a tabela usa um padrão "
            "com colunas a mais); "
            "'cruzar_com' (lista de OUTROS indicadores consultados junto, "
            "com os mesmos filtros e período, e juntados numa tabela só) "
            "— use quando a pergunta combinar indicadores, ex: 'qual "
            "filial teve o maior NPS e bateu a meta' = {\"indicador\": "
            "\"nps\", \"cruzar_com\": [\"meta\"], \"agrupar_por\": "
            "[\"filial\"], \"filtros_calculados\": [{\"campo\": "
            "\"percentual_atingimento\", \"operador\": \">=\", "
            "\"valor\": 100}], \"ordenar_por\": {\"campo\": \"nps\", "
            "\"limite\": 1}}. O resultado traz os campos de todos os "
            "indicadores, e 'filtros_calculados'/'ordenar_por' podem usar "
            "qualquer um deles. Só cruza agrupando por filial, estado, "
            "mes ou ano (nunca rca, supervisor ou dia). Campos que só "
            "existem ao cruzar certos indicadores (já calculados pelo "
            "sistema, NUNCA calcule você mesma(o)):\n"
            f"{gerar_descricao_cruzamentos()}\n"
            "Indicadores disponíveis nesta ferramenta:\n"
            f"{gerar_descricao_indicadores()}\n"
            "Indicadores que NÃO estão nessa lista (ex: desconto, "
            "inadimplência, clientes) ainda não estão disponíveis — "
            "nesse caso escolha 'fora_do_escopo'."
        ),
        "argumentos_obrigatorios": ["indicador"],
        "argumentos_opcionais": [
            "periodo",
            "periodo_personalizado",
            "filtros",
            "agrupar_por",
            "comparar_com",
            "comparar_com_personalizado",
            "cruzar_com",
            "comparar_filtros",
            "colunas",
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