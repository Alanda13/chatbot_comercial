"""
Catálogo central de indicadores comerciais.

Cada indicador registra:
- carregar: função Python que busca os dados brutos (DataFrame) — None
  quando ainda não há fonte real conectada; nesse caso o orquestrador
  levanta um erro claro em vez de inventar dado.
- carregar_forma_pagamento (opcional): fonte alternativa usada só
  quando o agrupamento/filtro pede a dimensão "forma_pagamento".
- granularidade_periodo: "mensal" (filtra por mes/ano) ou "diaria"
  (filtra por intervalo de datas) — usado por
  orquestrador.resolver_periodo pra saber que vocabulário de período
  usar pra esse indicador.
- campos: nome do campo (o que aparece no resultado) -> (coluna do
  DataFrame, agregação pandas: "sum", "mean"...).
- dimensoes: nome da dimensão (o que a IA pode agrupar/filtrar) ->
  coluna do DataFrame.
- resolver_dimensao (opcional): nome da dimensão -> função que
  resolve o valor informado pela IA (nome de filial/RCA, com
  correspondência aproximada) pro valor real usado na base —
  reaproveita a mesma lógica já usada pelas ferramentas antigas, em
  vez de duplicar.
- derivados (opcional): campos calculados a partir dos campos brutos
  já agregados, usando funções puras de motor_metricas.py.
- unidade: como formatar o resultado.
- exibicao (opcional): nome do campo/derivado -> como mostrar esse
  campo numa tabela ("tipo": moeda/percentual/texto, "rotulo": título
  da coluna, e "sempre": True OU "palavras": [...] pra decidir quando
  a coluna aparece). Usado por gerar_colunas_tabela() pra montar a
  configuração de tabela do app.py automaticamente — um indicador
  novo não exige editar app.py à mão, só preencher isso aqui.

Baseado nos rascunhos do gestor (catalogo.py/motor_metricas.py/
orquestrador.py, em Downloads\\) e no documento
prompt_claude_code_migracao.md, adaptados às fontes de dado reais do
projeto: CSV via pandas para faturamento/faturamento diário/meta/meta de
tonelada, e Azure SQL (carregado inteiro pro pandas) para o NPS.

Indicadores sem "carregar" real (desconto, inadimplencia, clientes)
ainda não têm nenhuma fonte de dado conectada.

Este arquivo é a ÚNICA fonte de verdade sobre o que o motor genérico
(orquestrador.py) sabe consultar. A IA nunca deve referenciar um
indicador ou dimensão que não esteja aqui.
"""
from src.faturamento_data import carregar_faturamento_mensal
from src.faturamento_diario_data import (
    carregar_faturamento_diario,
    carregar_faturamento_diario_forma_pagamento,
    construir_mapa_rca_nome,
    resolver_codigos_rca,
)
from src.filiais import resolver_estado, resolver_nome_filial
from src.metas_data import resolver_codigos_supervisor
from src.nps_data import carregar_avaliacoes_nps
from src.meta_tonelada_data import (
    carregar_meta_tonelada,
    resolver_nomes_rca_tonelada,
)

DIMENSOES_VALIDAS = [
    "filial", "estado", "rca", "supervisor", "mes", "ano", "dia",
    "forma_pagamento",
]

PERIODOS_VALIDOS = [
    "hoje", "ontem", "semana_atual", "mes_atual", "ano_atual",
    "mes_anterior", "mesmo_mes_ano_anterior", "personalizado",
    # Especial: só faz sentido em "comparar_com" — usa o(s) ano(s) já
    # filtrados na consulta, menos 1 (ex: filtros={"ano": [2025]} +
    # comparar_com="ano_anterior_ao_filtro" compara com 2024).
    "ano_anterior_ao_filtro",
]

INDICADORES = {
    "faturamento": {
        "carregar": carregar_faturamento_mensal,
        "granularidade_periodo": "mensal",
        "campos": {
            "faturamento": ("VENDA_LIQ", "sum"),
            "venda_bruta": ("VENDA_BRUTA", "sum"),
            "valor_desconto": ("VALORDESC", "sum"),
            "peso_liquido": ("PESOLIQ", "sum"),
            "quantidade_notas": ("QT_NOTAS", "sum"),
        },
        "dimensoes": {
            "filial": "FILIAL", "estado": "ESTADO", "rca": "COD_RCA",
            "mes": "MES", "ano": "ANO",
        },
        "resolver_dimensao": {
            "filial": resolver_nome_filial,
            "estado": resolver_estado,
            "rca": resolver_codigos_rca,
        },
        "rca_nome_mapa": construir_mapa_rca_nome,
        "rca_requer_meta_cadastrada": True,
        "derivados": [
            {
                "nome": "toneladas",
                "formula": "calcular_toneladas",
                "campos": ("peso_liquido",),
            },
        ],
        "campo_principal": "faturamento",
        "unidade": "R$",
        "exibicao": {
            "faturamento": {"tipo": "moeda", "rotulo": "Faturamento", "palavras": ["fatur"]},
            "venda_bruta": {"tipo": "moeda", "rotulo": "Venda Bruta", "palavras": ["venda bruta"]},
            "valor_desconto": {"tipo": "moeda", "rotulo": "Desconto", "palavras": ["descont"]},
            "peso_liquido": {"tipo": "texto", "rotulo": "Peso Líquido", "palavras": ["peso"]},
            "quantidade_notas": {"tipo": "texto", "rotulo": "Qtd. Notas", "palavras": ["nota"]},
            "toneladas": {"tipo": "texto", "rotulo": "Toneladas", "palavras": ["tonelada"]},
        },
    },
    "faturamento_diario": {
        "carregar": carregar_faturamento_diario,
        "carregar_forma_pagamento": carregar_faturamento_diario_forma_pagamento,
        "granularidade_periodo": "diaria",
        "campos": {
            "faturamento": ("VENDA_LIQ", "sum"),
            "venda_bruta": ("VENDA_BRUTA", "sum"),
            "valor_desconto": ("VALORDESC", "sum"),
            "quantidade_notas": ("QT_NOTAS", "sum"),
        },
        "dimensoes": {
            "filial": "FILIAL", "estado": "ESTADO", "rca": "COD_RCA",
            "dia": "DATA", "forma_pagamento": "COBRANCA",
        },
        "resolver_dimensao": {
            "filial": resolver_nome_filial,
            "estado": resolver_estado,
            "rca": resolver_codigos_rca,
        },
        "rca_nome_mapa": construir_mapa_rca_nome,
        "rca_requer_meta_cadastrada": True,
        "campo_principal": "faturamento",
        "unidade": "R$",
        "exibicao": {
            "faturamento": {"tipo": "moeda", "rotulo": "Faturamento", "palavras": ["fatur"]},
            "venda_bruta": {"tipo": "moeda", "rotulo": "Venda Bruta", "palavras": ["venda bruta"]},
            "valor_desconto": {"tipo": "moeda", "rotulo": "Desconto", "palavras": ["descont"]},
            "quantidade_notas": {"tipo": "texto", "rotulo": "Qtd. Notas", "palavras": ["nota"]},
        },
    },
    "meta": {
        "carregar": carregar_faturamento_mensal,
        "granularidade_periodo": "mensal",
        "campos": {
            "valor_meta": ("VALOR_META", "sum"),
            "faturamento_realizado": ("VENDA_LIQ", "sum"),
        },
        "dimensoes": {
            "filial": "FILIAL", "estado": "ESTADO", "rca": "COD_RCA",
            "supervisor": "COD_SUPERVISOR", "mes": "MES", "ano": "ANO",
        },
        "resolver_dimensao": {
            "filial": resolver_nome_filial,
            "estado": resolver_estado,
            "rca": resolver_codigos_rca,
            "supervisor": resolver_codigos_supervisor,
        },
        "rca_nome_mapa": construir_mapa_rca_nome,
        "rca_requer_meta_cadastrada": True,
        "derivados": [
            {
                "nome": "percentual_atingimento",
                "formula": "calcular_atingimento_meta",
                "campos": ("faturamento_realizado", "valor_meta"),
            },
            {
                "nome": "falta_para_meta",
                "formula": "calcular_valor_faltante",
                "campos": ("valor_meta", "faturamento_realizado"),
            },
        ],
        "campo_principal": "faturamento_realizado",
        "necessidade_diaria_campo": "falta_para_meta",
        "unidade": "R$",
        "exibicao": {
            "valor_meta": {"tipo": "moeda", "rotulo": "Meta", "sempre": True},
            "faturamento_realizado": {"tipo": "moeda", "rotulo": "Faturamento Realizado", "sempre": True},
            "percentual_atingimento": {"tipo": "percentual", "rotulo": "Atingimento", "sempre": True},
            "falta_para_meta": {"tipo": "moeda", "rotulo": "Falta para Meta", "palavras": ["falta"]},
            "necessidade_diaria": {"tipo": "moeda", "rotulo": "Necessidade Diária", "palavras": ["necessidade", "por dia"]},
        },
    },

    "meta_tonelada": {
        "carregar": carregar_meta_tonelada,
        "granularidade_periodo": "mensal",
        "campos": {
            # "Meta Tonelada - Filial" se repete em toda linha de RCA
            # da mesma filial/mês (é um valor por filial, não por
            # vendedor) — "unico_por" descarta as linhas repetidas
            # antes de somar, senão o valor sairia multiplicado pela
            # quantidade de RCAs daquela filial.
            "meta_tonelada_filial": (
                "Meta Tonelada - Filial",
                "sum",
                {"unico_por": ("FILIAL", "ANO", "MES")},
            ),
            "meta_tonelada_rca": ("Meta Tonelada - RCA", "sum"),
        },
        "dimensoes": {
            "filial": "FILIAL", "estado": "ESTADO", "rca": "RCA",
            "mes": "MES", "ano": "ANO",
        },
        "resolver_dimensao": {
            "filial": resolver_nome_filial,
            "estado": resolver_estado,
            "rca": resolver_nomes_rca_tonelada,
        },
        "unidade": "toneladas",
        "exibicao": {
            "meta_tonelada_filial": {"tipo": "texto", "rotulo": "Meta Tonelada (Filial)", "sempre": True},
            "meta_tonelada_rca": {"tipo": "texto", "rotulo": "Meta Tonelada (RCA)", "palavras": ["rca", "vendedor"]},
        },
    },

    "nps": {
        "carregar": carregar_avaliacoes_nps,
        # NPS é consultado por datas quaisquer ("mês passado", um
        # intervalo) — a granularidade "diaria" aceita isso, e as
        # dimensões mes/ano continuam disponíveis pra agrupar/filtrar.
        "granularidade_periodo": "diaria",
        "campos": {
            "total_respostas": ("RESPOSTA", "sum"),
            "total_promotores": ("PROMOTOR", "sum"),
            "total_neutros": ("NEUTRO", "sum"),
            "total_detratores": ("DETRATOR", "sum"),
        },
        "dimensoes": {
            "filial": "FILIAL", "estado": "ESTADO", "mes": "MES",
            "ano": "ANO", "dia": "DATA",
        },
        "resolver_dimensao": {
            "filial": resolver_nome_filial,
            "estado": resolver_estado,
        },
        # Os percentuais e o NPS são calculados em cima das SOMAS (nunca
        # a média de NPS de vários períodos/filiais, que daria errado).
        "derivados": [
            {
                "nome": "percentual_promotores",
                "formula": "calcular_participacao",
                "campos": ("total_promotores", "total_respostas"),
            },
            {
                "nome": "percentual_neutros",
                "formula": "calcular_participacao",
                "campos": ("total_neutros", "total_respostas"),
            },
            {
                "nome": "percentual_detratores",
                "formula": "calcular_participacao",
                "campos": ("total_detratores", "total_respostas"),
            },
            {
                "nome": "nps",
                "formula": "calcular_nps",
                "campos": (
                    "total_promotores", "total_detratores", "total_respostas",
                ),
            },
        ],
        "campo_principal": "nps",
        "unidade": "pontos",
        "exibicao": {
            "nps": {"tipo": "texto", "rotulo": "NPS", "sempre": True},
            "total_respostas": {"tipo": "texto", "rotulo": "Respostas", "palavras": ["resposta"]},
            "total_promotores": {"tipo": "texto", "rotulo": "Promotores", "palavras": ["promotor"]},
            "total_neutros": {"tipo": "texto", "rotulo": "Neutros", "palavras": ["neutro"]},
            "total_detratores": {"tipo": "texto", "rotulo": "Detratores", "palavras": ["detrator"]},
            "percentual_promotores": {"tipo": "percentual", "rotulo": "% Promotores", "palavras": ["promotor"]},
            "percentual_neutros": {"tipo": "percentual", "rotulo": "% Neutros", "palavras": ["neutro"]},
            "percentual_detratores": {"tipo": "percentual", "rotulo": "% Detratores", "palavras": ["detrator"]},
        },
    },
    # Abaixo, indicadores registrados no catálogo mas SEM fonte real
    # conectada ainda ("carregar": None) — documentam o que o sistema
    # deveria ter (desconto, inadimplencia, clientes: ainda sem
    # nenhuma fonte real, CSV ou view Oracle/WinThor, no projeto).
    "desconto": {
        "carregar": None,
        "granularidade_periodo": "mensal",
        "campos": {"faturamento_tabela": None, "faturamento_liquido": None},
        "dimensoes": {"filial": None, "rca": None},
        "derivados": [
            {
                "nome": "percentual_desconto",
                "formula": "calcular_desconto",
                "campos": ("faturamento_tabela", "faturamento_liquido"),
            },
        ],
        "unidade": "%",
    },
    "inadimplencia": {
        "carregar": None,
        "granularidade_periodo": "mensal",
        "campos": {"valor_inadimplente": None, "faturamento_liquido": None},
        "dimensoes": {"filial": None},
        "derivados": [
            {
                "nome": "percentual_inadimplencia",
                "formula": "calcular_inadimplencia",
                "campos": ("valor_inadimplente", "faturamento_liquido"),
            },
        ],
        "unidade": "%",
    },
    "clientes": {
        "carregar": None,
        "granularidade_periodo": "mensal",
        "campos": {"valor_compra": None, "qtd_compras": None},
        "dimensoes": {"cliente": None, "filial": None, "rca": None},
        "unidade": "R$ / qtd",
    },
}

# Fórmulas que dependem de DOIS indicadores ao mesmo tempo (ex: toneladas
# vendidas ÷ meta de tonelada). O orquestrador calcula esses derivados
# depois de juntar os indicadores, só quando a consulta cruza todos os
# indicadores listados em "indicadores" (campo "cruzar_com").
CRUZAMENTOS = [
    {
        "indicadores": ("faturamento", "meta_tonelada"),
        "derivados": [
            {
                "nome": "percentual_atingimento_tonelada",
                "formula": "calcular_atingimento_meta",
                "campos": ("toneladas", "meta_tonelada_filial"),
                "descricao": (
                    "% de atingimento da meta de tonelada (toneladas "
                    "vendidas ÷ meta de tonelada da filial) — use pra "
                    "'quem bateu a meta de tonelada'"
                ),
            },
            {
                "nome": "falta_para_meta_tonelada",
                "formula": "calcular_valor_faltante",
                "campos": ("meta_tonelada_filial", "toneladas"),
                "descricao": "toneladas que faltam pra bater a meta de tonelada",
            },
        ],
        "exibicao": {
            "percentual_atingimento_tonelada": {
                "tipo": "percentual", "rotulo": "Atingimento Tonelada",
                "sempre": True,
            },
            "falta_para_meta_tonelada": {
                "tipo": "texto", "rotulo": "Falta para Meta (t)",
                "palavras": ["falta"],
            },
        },
    },
]


def indicador_existe(nome: str) -> bool:
    return nome in INDICADORES


def dimensao_permitida(indicador: str, dimensao: str) -> bool:
    if not indicador_existe(indicador):
        return False
    return dimensao in INDICADORES[indicador]["dimensoes"]


def gerar_descricao_indicadores() -> str:
    """
    Gera o texto com os indicadores conectados ao motor genérico
    (carregar preenchido), pra IA saber o que pode consultar via a
    ferramenta "consultar_dados_comerciais". Indicadores com
    carregar=None não entram aqui — a ferramenta ainda não consegue
    buscar dado real pra eles, então não devem ser oferecidos à IA por
    esse caminho.
    """
    linhas = []

    for nome, definicao in INDICADORES.items():
        if definicao.get("carregar") is None:
            continue

        campos = ", ".join(definicao["campos"])
        dimensoes = ", ".join(definicao["dimensoes"])

        linhas.append(
            f"  * {nome} ({definicao['unidade']}) — período "
            f"{definicao['granularidade_periodo']}; campos: "
            f"[{campos}]; dimensões para filtrar/agrupar: [{dimensoes}]"
        )

    return "\n".join(linhas)


def gerar_descricao_cruzamentos() -> str:
    """
    Texto com os campos calculados ao cruzar indicadores, pra IA saber
    que eles existem e com qual "cruzar_com" aparecem.
    """
    return "\n".join(
        f"  * {' + '.join(cruzamento['indicadores'])}: "
        f"{derivado['nome']} ({derivado['descricao']})"
        for cruzamento in CRUZAMENTOS
        for derivado in cruzamento["derivados"]
    )


def gerar_colunas_tabela() -> list[dict]:
    """
    Monta a lista de colunas (coluna, tipo, rótulo, e "sempre" ou
    "palavras") pra exibição em tabela, juntando o "exibicao" de todos
    os indicadores conectados (carregar preenchido) e dos cruzamentos —
    usada por app.py pra montar a config de "consultar_dados_comerciais"
    sem precisar de um bloco escrito à mão por indicador. Cada indicador
    novo só precisa preencher "exibicao" aqui; a tabela do app.py
    passa a reconhecer as colunas dele automaticamente.

    Quando a consulta usa "comparar_com", o motor cria, pra cada campo,
    "{campo}_anterior", "diferenca_{campo}" e "percentual_{campo}" — as
    três colunas são geradas aqui pra TODO campo (assim qualquer campo
    pedido em "colunas" tem rótulo e formato). No padrão, só as do campo
    principal do indicador aparecem sozinhas ("sempre").
    """
    exibicoes = [
        cruzamento["exibicao"] for cruzamento in CRUZAMENTOS
    ] + [
        definicao.get("exibicao", {})
        for definicao in INDICADORES.values()
        if definicao.get("carregar") is not None
    ]
    campos_principais = {
        definicao.get("campo_principal")
        for definicao in INDICADORES.values()
        if definicao.get("carregar") is not None
    }

    colunas_por_nome: dict[str, dict] = {}

    for exibicao in exibicoes:
        for nome_campo, especificacao in exibicao.items():
            colunas_por_nome.setdefault(
                nome_campo, {"coluna": nome_campo, **especificacao}
            )

    for nome_campo, especificacao in list(colunas_por_nome.items()):
        tipo = especificacao["tipo"]
        rotulo = especificacao["rotulo"]
        tipo_diferenca = {
            "percentual": "percentual_com_sinal", "texto": "numero_com_sinal",
        }.get(tipo, tipo)
        sempre = {"sempre": True} if nome_campo in campos_principais else {}

        for nome, tipo_coluna, rotulo_coluna in (
            (f"{nome_campo}_anterior", tipo, f"{rotulo} (anterior)"),
            (f"diferenca_{nome_campo}", tipo_diferenca, f"Diferença {rotulo}"),
            (f"percentual_{nome_campo}", "percentual_com_sinal", f"Variação {rotulo}"),
        ):
            colunas_por_nome.setdefault(
                nome,
                {"coluna": nome, "tipo": tipo_coluna, "rotulo": rotulo_coluna, **sempre},
            )

    return list(colunas_por_nome.values())
