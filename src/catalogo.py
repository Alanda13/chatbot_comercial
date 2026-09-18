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
projeto: CSV via pandas para faturamento/faturamento diário/meta.

Indicadores sem "carregar" real (meta_tonelada, nps, desconto,
inadimplencia, clientes) continuam servidos pelas ferramentas antigas
enquanto não são conectados ao motor genérico — motivo de cada um
descrito no comentário logo abaixo de INDICADORES.

Este arquivo é a ÚNICA fonte de verdade sobre o que o motor genérico
(orquestrador.py) sabe consultar. A IA nunca deve referenciar um
indicador ou dimensão que não esteja aqui.
"""
from src.faturamento_data import carregar_faturamento_8280
from src.faturamento_diario_data import (
    carregar_faturamento_8302,
    carregar_faturamento_8302_cobranca,
    construir_mapa_rca_nome,
    resolver_codigos_rca,
    resolver_nome_filial_diario,
)
from src.faturamento_tools import resolver_nome_filial
from src.metas_data import resolver_codigos_supervisor
from src.meta_tonelada_data import (
    carregar_meta_tonelada,
    resolver_nome_filial_tonelada,
    resolver_nomes_rca_tonelada,
)

DIMENSOES_VALIDAS = [
    "filial", "rca", "supervisor", "mes", "ano", "dia", "forma_pagamento",
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
        "carregar": carregar_faturamento_8280,
        "granularidade_periodo": "mensal",
        "campos": {
            "faturamento": ("VENDA_LIQ", "sum"),
            "venda_bruta": ("VENDA_BRUTA", "sum"),
            "valor_desconto": ("VALORDESC", "sum"),
            "peso_liquido": ("PESOLIQ", "sum"),
            "quantidade_notas": ("QT_NOTAS", "sum"),
        },
        "dimensoes": {
            "filial": "FILIAL", "rca": "COD_RCA", "mes": "MES", "ano": "ANO",
        },
        "resolver_dimensao": {
            "filial": resolver_nome_filial,
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
        "carregar": carregar_faturamento_8302,
        "carregar_forma_pagamento": carregar_faturamento_8302_cobranca,
        "granularidade_periodo": "diaria",
        "campos": {
            "faturamento": ("VENDA_LIQ", "sum"),
            "venda_bruta": ("VENDA_BRUTA", "sum"),
            "valor_desconto": ("VALORDESC", "sum"),
            "quantidade_notas": ("QT_NOTAS", "sum"),
        },
        "dimensoes": {
            "filial": "FILIAL", "rca": "COD_RCA", "dia": "DATA",
            "forma_pagamento": "COBRANCA",
        },
        "resolver_dimensao": {
            "filial": resolver_nome_filial_diario,
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
        "carregar": carregar_faturamento_8280,
        "granularidade_periodo": "mensal",
        "campos": {
            "valor_meta": ("VALOR_META", "sum"),
            "faturamento_realizado": ("VENDA_LIQ", "sum"),
        },
        "dimensoes": {
            "filial": "FILIAL", "rca": "COD_RCA",
            "supervisor": "COD_SUPERVISOR", "mes": "MES", "ano": "ANO",
        },
        "resolver_dimensao": {
            "filial": resolver_nome_filial,
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
            "filial": "FILIAL", "rca": "RCA", "mes": "MES", "ano": "ANO",
        },
        "resolver_dimensao": {
            "filial": resolver_nome_filial_tonelada,
            "rca": resolver_nomes_rca_tonelada,
        },
        "unidade": "toneladas",
        "exibicao": {
            "meta_tonelada_filial": {"tipo": "texto", "rotulo": "Meta Tonelada (Filial)", "sempre": True},
            "meta_tonelada_rca": {"tipo": "texto", "rotulo": "Meta Tonelada (RCA)", "sempre": True},
        },
    },

    # Abaixo, indicadores registrados no catálogo mas SEM fonte real
    # conectada ainda ("carregar": None) — continuam sendo atendidos
    # pelas ferramentas antigas equivalentes, não pelo motor genérico:
    # - nps: vem de Azure SQL via cursor manual (queries.py), não de
    #   um DataFrame pandas — precisa de um loader que traga as
    #   respostas brutas antes de caber no motor genérico.
    # - desconto, inadimplencia, clientes: ainda sem nenhuma fonte
    #   real (CSV ou view Oracle/WinThor) conectada no projeto.
    "nps": {
        "carregar": None,
        "granularidade_periodo": "mensal",
        "campos": {"nps": None},
        "dimensoes": {"filial": None, "mes": None, "ano": None},
        "unidade": "pontos",
    },
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


def gerar_colunas_tabela() -> list[dict]:
    """
    Monta a lista de colunas (coluna, tipo, rótulo, e "sempre" ou
    "palavras") pra exibição em tabela, juntando o "exibicao" de todos
    os indicadores conectados (carregar preenchido) — usada por
    app.py pra montar a config de "consultar_dados_comerciais" sem
    precisar de um bloco escrito à mão por indicador. Cada indicador
    novo só precisa preencher "exibicao" aqui; a tabela do app.py
    passa a reconhecer as colunas dele automaticamente.
    """
    colunas_por_nome: dict[str, dict] = {}

    for definicao in INDICADORES.values():
        if definicao.get("carregar") is None:
            continue

        for nome_campo, especificacao in definicao.get("exibicao", {}).items():
            if nome_campo not in colunas_por_nome:
                colunas_por_nome[nome_campo] = {
                    "coluna": nome_campo,
                    **especificacao,
                }

    return list(colunas_por_nome.values())
