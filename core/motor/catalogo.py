"""
Catálogo central de indicadores comerciais.

Cada indicador registra:
- carregar: função Python que busca os dados brutos (DataFrame) — None
  quando ainda não há fonte real conectada; nesse caso o orquestrador
  levanta um erro claro em vez de inventar dado.
- fontes_por_dimensao (opcional): dimensão -> fonte alternativa,
  usada só quando o agrupamento/filtro pede aquela dimensão (ex:
  "forma_pagamento", "cliente") — arquivos maiores que só são lidos
  quando a pergunta precisa deles.
- fontes_combinadas (opcional): arquivos que juntam dimensões de fontes
  diferentes (ex: cliente e produto), usados quando a pergunta pede as
  duas; cada um diz o que tem em `tambem_tem`.
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

Este arquivo é a ÚNICA fonte de verdade sobre o que o motor genérico
(orquestrador.py) sabe consultar. A IA nunca deve referenciar um
indicador ou dimensão que não esteja aqui.
"""
from core.repositories.cliente_repository import (
    carregar_desconto_cliente,
    resolver_codigos_cliente,
    resolver_empresas,
)
from core.repositories.faturamento_repository import carregar_faturamento_mensal
from core.repositories.cliente_produto_repository import carregar_cliente_produto
from core.repositories.inadimplencia_repository import (
    carregar_inadimplencia,
    descrever_fechamento,
    descrever_sem_periodo,
)
from core.repositories.situacao_cliente_repository import (
    carregar_situacao_clientes,
    periodo_da_frequencia,
)
from core.repositories.venda_repository import carregar_desconto_venda, carregar_vendas_com_devolucao, resolver_vendas
from core.repositories.produto_repository import (
    carregar_desconto_produto,
    resolver_familias,
    resolver_grupos,
    resolver_produtos,
)
from core.repositories.faturamento_diario_repository import (
    carregar_faturamento_diario,
    carregar_faturamento_diario_forma_pagamento,
    construir_mapa_rca_nome,
    resolver_codigos_rca,
)
from core.repositories.filiais_repository import resolver_estado, resolver_nome_filial
from core.repositories.metas_repository import resolver_codigos_supervisor
from core.repositories.nps_repository import carregar_avaliacoes_nps
from core.repositories.meta_tonelada_repository import (
    carregar_meta_tonelada,
    resolver_nomes_rca_tonelada,
)

DIMENSOES_VALIDAS = [
    "filial", "estado", "rca", "supervisor", "mes", "ano", "dia",
    "forma_pagamento", "cliente", "empresa", "produto", "familia", "grupo",
    "venda",
]

# Colunas que DESCREVEM o item de uma dimensão (vêm junto quando se
# agrupa por ela, mas não são agrupamentos novos): nome do campo no
# resultado -> (coluna do DataFrame, título na tabela). Ex: agrupar por
# "cliente" (o código) traz também nome, CNPJ e cidade da loja. Só entram
# as colunas que existem na base do indicador (o arquivo de cliente, por
# exemplo, não tem o nome do supervisor).
# Só no indicador clientes, das notas do dia da última compra (desde 2025).
_DETALHES_DA_ULTIMA_COMPRA = {
    "valor_ultima_compra": ("VALOR_ULTIMA_COMPRA", "Valor da última compra"),
    "nota_ultima_compra": ("NOTA_ULTIMA_COMPRA", "Nota da última compra"),
    "pedido_ultima_compra": ("PEDIDO_ULTIMA_COMPRA", "Pedido da última compra"),
    "rca_ultima_compra": ("NOME_RCA_ULTIMA_COMPRA", "RCA da última compra"),
}
# Atributos que só entram na tabela quando a resposta fala neles (a lista
# de clientes ficaria larga demais): campo -> palavras.
ATRIBUTOS_SO_SE_CITADOS = {
    "valor_ultima_compra": ["valor"],
    "nota_ultima_compra": ["nota"],
    "pedido_ultima_compra": ["pedido"],
    "rca_ultima_compra": ["rca", "vendedor", "vendid"],
}

ATRIBUTOS_DIMENSAO = {
    "supervisor": {
        "supervisor_nome": ("NOME_SUPERVISOR", "Supervisor"),
    },
    "cliente": {
        "cliente_nome": ("CLIENTE", "Cliente"),
        "cnpj": ("CNPJ", "CNPJ/CPF"),
        "cidade": ("CIDADE", "Cidade"),
        # Só no indicador clientes (os outros arquivos não têm essas colunas).
        "situacao": ("SITUACAO", "Situação"),
        "ultima_compra": ("ULTIMA_COMPRA", "Última compra"),
        "filial_ultima_compra": ("FILIAL_ULTIMA_COMPRA", "Filial da última compra"),
        **_DETALHES_DA_ULTIMA_COMPRA,
    },
    "produto": {
        "produto_nome": ("PRODUTO", "Produto"),
        "produto_familia": ("FAMILIA", "Família"),
        "produto_grupo": ("GRUPO", "Grupo"),
    },
    "familia": {
        "familia_grupo": ("GRUPO", "Grupo"),
    },
    "venda": {
        "venda_nota": ("NUMNOTA", "Nota"),
        "venda_pedido": ("NUMPED", "Pedido"),
        "venda_data": ("DATA_TEXTO", "Data"),
        "venda_cliente": ("CLIENTE", "Cliente"),
        "venda_rca": ("NOME_RCA", "RCA"),
        # o nº da nota se repete entre filiais: a filial diz qual é qual
        "venda_filial": ("FILIAL", "Filial da nota"),
    },
    "empresa": {
        # "Cliente": a empresa pode ser uma pessoa (CPF), ex: Consumidor Final.
        "empresa_nome": ("NOME_EMPRESA", "Cliente"),
        "cnpj_empresa": ("CNPJ_EMPRESA", "CNPJ (início)"),
        # Só no indicador clientes: o último dia em que alguma loja comprou,
        # com todas as lojas que compraram nele.
        "ultima_compra": ("ULTIMA_COMPRA", "Última compra"),
        "filial_ultima_compra": ("FILIAL_ULTIMA_COMPRA_EMPRESA", "Filial da última compra"),
        **{
            campo: (f"{coluna}_EMPRESA", rotulo)
            for campo, (coluna, rotulo) in _DETALHES_DA_ULTIMA_COMPRA.items()
        },
    },
}

# Item com várias linhas (empresa com várias lojas, cliente em vários
# meses): os atributos vêm da linha mais recente por esta coluna, quando o
# arquivo a tem.
COLUNA_DO_MAIS_RECENTE = "DATA_ULTIMA_COMPRA"

PERIODOS_VALIDOS = [
    "hoje", "ontem", "semana_atual", "semana_anterior", "mes_atual",
    "ano_atual", "mes_anterior", "ano_anterior", "mesmo_mes_ano_anterior",
    "personalizado",
    # Especial: só faz sentido em "comparar_com" — usa o(s) ano(s) já
    # filtrados na consulta, menos 1 (ex: filtros={"ano": [2025]} +
    # comparar_com="ano_anterior_ao_filtro" compara com 2024).
    "ano_anterior_ao_filtro",
]

# Ticket médio = faturamento ÷ nº de notas. Por produto não existe: uma nota
# tem vários produtos (o arquivo por produto não tem nº de notas).
_TICKET_MEDIO = {
    "nome": "ticket_medio",
    "formula": "calcular_ticket_medio",
    "campos": ("faturamento", "quantidade_notas"),
}
_EXIBICAO_TICKET_MEDIO = {"tipo": "moeda", "rotulo": "Ticket Médio", "palavras": ["ticket"]}

INDICADORES = {
    "faturamento": {
        "carregar": carregar_faturamento_mensal,
        # Por cliente/produto: os mesmos arquivos do desconto, que trazem a
        # venda e a devolução (VENDA_LIQ) — sem peso nem nº de notas, que
        # ficam de fora nessas consultas.
        "fontes_por_dimensao": {
            "cliente": carregar_desconto_cliente,
            "empresa": carregar_desconto_cliente,
            "produto": carregar_desconto_produto,
            "familia": carregar_desconto_produto,
            "grupo": carregar_desconto_produto,
        },
        # Cliente/empresa com produto/família/grupo (mix de produtos), desde 2025.
        "fontes_combinadas": (carregar_cliente_produto,),
        "granularidade_periodo": "mensal",
        "campos": {
            "faturamento": ("VENDA_LIQ", "sum"),
            "venda_bruta": ("VENDA_BRUTA", "sum"),
            "valor_desconto": ("VALORDESC", "sum"),
            "peso_liquido": ("PESOLIQ", "sum"),
            "quantidade_notas": ("QT_NOTAS", "sum"),
            # Quantos produtos diferentes: pedido, usa um arquivo com produto
            # ("precisa_de"); agrupado por produto, é 1 em toda linha ("conta").
            "produtos_diferentes": ("CODPROD", "nunique", {"conta": "produto", "precisa_de": "produto"}),
        },
        "dimensoes": {
            "filial": "FILIAL", "estado": "ESTADO", "rca": "COD_RCA",
            "mes": "MES", "ano": "ANO",
            "cliente": "CODCLI", "empresa": "EMPRESA",
            "produto": "CODPROD", "familia": "FAMILIA", "grupo": "GRUPO",
        },
        "resolver_dimensao": {
            "filial": resolver_nome_filial,
            "estado": resolver_estado,
            "rca": resolver_codigos_rca,
            "cliente": resolver_codigos_cliente,
            "empresa": resolver_empresas,
            "produto": resolver_produtos,
            "familia": resolver_familias,
            "grupo": resolver_grupos,
        },
        "rca_nome_mapa": construir_mapa_rca_nome,
        "rca_requer_meta_cadastrada": True,
        # "Quem MENOS faturou": o RCA com meta cadastrada que não vendeu nada
        # (R$ 0,00) sai da lista e vem à parte. Totais não mudam.
        "menor_ignora": {
            "ordem_por": ("faturamento", "venda_bruta"),
            "campo": "venda_bruta", "abaixo_de": 0.01,
            "motivo": "não tiveram venda no período (só devolução)",
            "motivo_por_dimensao": {
                "rca": "têm meta cadastrada, mas não venderam nada no período",
            },
            # Faturamento negativo (devolução maior que a venda do mês) também vem
            # à parte.
            "tambem": [{
                "ordem_por": ("faturamento",),
                "campo": "faturamento", "abaixo_de": 0.01,
                "motivo": (
                    "devolveram tudo o que compraram ou mais (devolução igual ou "
                    "maior que a venda no período: faturamento zero ou negativo)"
                ),
            }],
        },
        "derivados": [
            {
                "nome": "toneladas",
                "formula": "calcular_toneladas",
                "campos": ("peso_liquido",),
            },
            _TICKET_MEDIO,
        ],
        "campo_principal": "faturamento",
        "unidade": "R$",
        "exibicao": {
            "faturamento": {"tipo": "moeda", "rotulo": "Faturamento", "palavras": ["fatur"]},
            "venda_bruta": {"tipo": "moeda", "rotulo": "Venda Bruta", "palavras": ["venda bruta"]},
            "valor_desconto": {"tipo": "moeda", "rotulo": "Desconto", "palavras": ["descont"]},
            "peso_liquido": {"tipo": "texto", "rotulo": "Peso Líquido", "palavras": ["peso"]},
            "quantidade_notas": {"tipo": "texto", "rotulo": "Qtd. Notas", "palavras": ["nota"]},
            "produtos_diferentes": {"tipo": "texto", "rotulo": "Produtos diferentes", "palavras": ["produtos diferentes", "mix"]},
            "toneladas": {"tipo": "texto", "rotulo": "Toneladas", "palavras": ["tonelada"]},
            "ticket_medio": _EXIBICAO_TICKET_MEDIO,
        },
    },
    "faturamento_diario": {
        "carregar": carregar_faturamento_diario,
        # Por cliente: as notas com a devolução de cada cliente (desde 2025).
        # Por venda: só as notas — a nota não traz devolução.
        "fontes_por_dimensao": {
            "forma_pagamento": carregar_faturamento_diario_forma_pagamento,
            "venda": carregar_desconto_venda,
            "cliente": carregar_vendas_com_devolucao,
            "empresa": carregar_vendas_com_devolucao,
        },
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
            "venda": "NUMTRANSVENDA", "cliente": "CODCLI", "empresa": "EMPRESA",
        },
        "resolver_dimensao": {
            "filial": resolver_nome_filial,
            "estado": resolver_estado,
            "rca": resolver_codigos_rca,
            "venda": resolver_vendas,
            "cliente": resolver_codigos_cliente,
            "empresa": resolver_empresas,
        },
        "rca_nome_mapa": construir_mapa_rca_nome,
        "rca_requer_meta_cadastrada": True,
        "derivados": [_TICKET_MEDIO],
        "campo_principal": "faturamento",
        "unidade": "R$",
        "exibicao": {
            "faturamento": {"tipo": "moeda", "rotulo": "Faturamento", "palavras": ["fatur"]},
            "venda_bruta": {"tipo": "moeda", "rotulo": "Venda Bruta", "palavras": ["venda bruta"]},
            "valor_desconto": {"tipo": "moeda", "rotulo": "Desconto", "palavras": ["descont"]},
            "quantidade_notas": {"tipo": "texto", "rotulo": "Qtd. Notas", "palavras": ["nota"]},
            "ticket_medio": _EXIBICAO_TICKET_MEDIO,
        },
    },
    "meta": {
        # Acumulado do ano corrente = só meses fechados; o mês em andamento
        # vem à parte (ver orquestrador._separar_mes_em_andamento).
        "acumulado_so_meses_fechados": True,
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
        # O que resume a meta numa tabela/comparação é o atingimento; a
        # variação mês a mês/ano a ano continua sendo a do faturamento.
        "campo_principal": "percentual_atingimento",
        "campo_variacao": "faturamento_realizado",
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
        # Acumulado do ano corrente = só meses fechados; o mês em andamento
        # vem à parte (ver orquestrador._separar_mes_em_andamento).
        "acumulado_so_meses_fechados": True,
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
    # Desconto = venda de tabela − venda bruta (rotina 8280 — ver
    # core/repositories/faturamento_repository.py e motor_metricas.calcular_desconto).
    # O % é calculado sobre as SOMAS (desconto total ÷ venda bruta total),
    # nunca a média dos % de cada filial/RCA.
    "desconto": {
        # "Quem MENOS deu desconto": desconto negativo (vendeu acima da
        # tabela mais do que descontou) e abaixo de R$ 1,00 (arredondamento
        # de meio centavo por item em kg/metro) saem da lista e vêm à parte.
        # Só muda a lista; os totais seguem iguais aos do WinThor (8280).
        "menor_ignora": {
            "ordem_por": ("valor_desconto", "percentual_desconto"),
            "campo": "valor_desconto", "abaixo_de": 0.0,
            "motivo": "desconto negativo: venderam acima da tabela mais do que deram de desconto",
            "tambem": [{
                "campo": "valor_desconto", "abaixo_de": 1.0,
                "motivo": "não deram desconto (abaixo de R$ 1,00 é só arredondamento)",
            }],
        },
        # Cruzado com outro indicador, a tabela mostra o desconto em R$ e em %.
        "colunas_no_cruzamento": ["valor_desconto", "percentual_desconto"],
        "carregar": carregar_faturamento_mensal,
        # Sem período, usa o ano atual (senão somaria desde 2020) e a resposta
        # avisa.
        "periodo_padrao": "ano_atual",
        # Uma venda (nota/pedido) já tem data: sem período assumido — senão
        # "a nota 245704" de 2025 não seria achada em "2026".
        "sem_periodo_padrao_com": ("venda",),
        # Por cliente/empresa: arquivo próprio (~1,2 milhão de linhas,
        # ver core/repositories/cliente_repository.py), lido só quando a pergunta pede.
        # Por produto/família/grupo: outro arquivo (core/repositories/produto_repository.py) —
        # grupo e família vêm da planilha BASE_PRODUTOS do comercial.
        "fontes_por_dimensao": {
            "cliente": carregar_desconto_cliente,
            "empresa": carregar_desconto_cliente,
            "produto": carregar_desconto_produto,
            "familia": carregar_desconto_produto,
            "grupo": carregar_desconto_produto,
            # Por venda (nota/pedido), desde 2025: core/repositories/venda_repository.py
            "venda": carregar_desconto_venda,
        },
        "fontes_combinadas": (carregar_cliente_produto,),
        "granularidade_periodo": "mensal",
        "campos": {
            # Mesmo nome e mesma coluna do campo do faturamento: num
            # cruzamento os dois viram UMA coluna só (ver
            # orquestrador._validar_cruzamento).
            "valor_desconto": ("VALORDESC", "sum"),
            "faturamento_tabela": ("VENDA_TABELA", "sum"),
            # Valor vendido (antes de devolução): no desconto por produto/
            # grupo/cliente é "quanto vendeu" — sem precisar cruzar indicador.
            "venda_bruta": ("VENDA_BRUTA", "sum"),
        },
        "dimensoes": {
            "filial": "FILIAL", "estado": "ESTADO", "rca": "COD_RCA",
            "supervisor": "COD_SUPERVISOR", "mes": "MES", "ano": "ANO",
            "cliente": "CODCLI", "empresa": "EMPRESA",
            "produto": "CODPROD", "familia": "FAMILIA", "grupo": "GRUPO",
            "venda": "NUMTRANSVENDA",
        },
        "resolver_dimensao": {
            "filial": resolver_nome_filial,
            "estado": resolver_estado,
            "rca": resolver_codigos_rca,
            "supervisor": resolver_codigos_supervisor,
            "cliente": resolver_codigos_cliente,
            "empresa": resolver_empresas,
            "produto": resolver_produtos,
            "familia": resolver_familias,
            "grupo": resolver_grupos,
            "venda": resolver_vendas,
        },
        "rca_nome_mapa": construir_mapa_rca_nome,
        "rca_requer_meta_cadastrada": True,
        "derivados": [
            {
                "nome": "percentual_desconto",
                "formula": "calcular_desconto",
                "campos": ("valor_desconto", "venda_bruta"),
            },
        ],
        "campo_principal": "percentual_desconto",
        # A variação mês a mês/ano a ano é do desconto em R$: a variação do
        # % (9,05% → 9,07% = "+0,22%") escondia uma queda de R$ 115 mil
        # pra R$ 19 mil, lida ao lado das colunas em R$.
        "campo_variacao": "valor_desconto",
        "unidade": "%",
        "exibicao": {
            "percentual_desconto": {"tipo": "percentual", "rotulo": "% Desconto", "sempre": True},
            "valor_desconto": {"tipo": "moeda", "rotulo": "Desconto", "palavras": ["descont"]},
            "faturamento_tabela": {"tipo": "moeda", "rotulo": "Faturamento de Tabela", "palavras": ["tabela"]},
            "venda_bruta": {"tipo": "moeda", "rotulo": "Venda Bruta", "palavras": ["venda bruta"]},
        },
    },
    # Desconto por DIA (hoje, ontem, semana, datas): mesma conta e mesma
    # fonte do "desconto" mensal, vinda do arquivo diário. Sem supervisor:
    # o arquivo diário não tem essa coluna.
    "desconto_diario": {
        # "Quem MENOS deu desconto": desconto negativo (vendeu acima da
        # tabela mais do que descontou) e abaixo de R$ 1,00 (arredondamento
        # de meio centavo por item em kg/metro) saem da lista e vêm à parte.
        # Só muda a lista; os totais seguem iguais aos do WinThor (8280).
        "menor_ignora": {
            "ordem_por": ("valor_desconto", "percentual_desconto"),
            "campo": "valor_desconto", "abaixo_de": 0.0,
            "motivo": "desconto negativo: venderam acima da tabela mais do que deram de desconto",
            "tambem": [{
                "campo": "valor_desconto", "abaixo_de": 1.0,
                "motivo": "não deram desconto (abaixo de R$ 1,00 é só arredondamento)",
            }],
        },
        # Cruzado com outro indicador, a tabela mostra o desconto em R$ e em %.
        "colunas_no_cruzamento": ["valor_desconto", "percentual_desconto"],
        "carregar": carregar_faturamento_diario,
        # Por venda (e por cliente, que o arquivo de venda também tem):
        # desde 2025 — ver core/repositories/venda_repository.py.
        "fontes_por_dimensao": {
            "venda": carregar_desconto_venda,
            "cliente": carregar_desconto_venda,
            "empresa": carregar_desconto_venda,
        },
        "granularidade_periodo": "diaria",
        "periodo_padrao": "ano_atual",
        "sem_periodo_padrao_com": ("venda",),
        "campos": {
            "valor_desconto": ("VALORDESC", "sum"),
            "faturamento_tabela": ("VENDA_TABELA", "sum"),
            # Valor vendido (antes de devolução): no desconto por produto/
            # grupo/cliente é "quanto vendeu" — sem precisar cruzar indicador.
            "venda_bruta": ("VENDA_BRUTA", "sum"),
        },
        "dimensoes": {
            "filial": "FILIAL", "estado": "ESTADO", "rca": "COD_RCA",
            "dia": "DATA",
            "venda": "NUMTRANSVENDA", "cliente": "CODCLI", "empresa": "EMPRESA",
        },
        "resolver_dimensao": {
            "filial": resolver_nome_filial,
            "estado": resolver_estado,
            "rca": resolver_codigos_rca,
            "venda": resolver_vendas,
            "cliente": resolver_codigos_cliente,
            "empresa": resolver_empresas,
        },
        "rca_nome_mapa": construir_mapa_rca_nome,
        "rca_requer_meta_cadastrada": True,
        "derivados": [
            {
                "nome": "percentual_desconto",
                "formula": "calcular_desconto",
                "campos": ("valor_desconto", "venda_bruta"),
            },
        ],
        "campo_principal": "percentual_desconto",
        "campo_variacao": "valor_desconto",
        "unidade": "%",
        "exibicao": {
            "percentual_desconto": {"tipo": "percentual", "rotulo": "% Desconto", "sempre": True},
            "valor_desconto": {"tipo": "moeda", "rotulo": "Desconto", "palavras": ["descont"]},
            "faturamento_tabela": {"tipo": "moeda", "rotulo": "Faturamento de Tabela", "palavras": ["tabela"]},
            "venda_bruta": {"tipo": "moeda", "rotulo": "Venda Bruta", "palavras": ["venda bruta"]},
        },
    },
    # Títulos vencidos e não pagos (regras em
    # core/repositories/inadimplencia_repository.py). Mês/ano = do
    # vencimento. "Oficial" = fechamento da controladoria (dia 10, 2 meses
    # depois); "em atraso" = hoje.
    "inadimplencia": {
        "carregar": carregar_inadimplencia,
        "granularidade_periodo": "mensal",
        "campos": {
            "valor_inadimplente": ("VALOR_INADIMPLENTE", "sum"),
            "titulos_inadimplentes": ("TITULO_INADIMPLENTE", "sum"),
            "clientes_inadimplentes": ("CLIENTE_INADIMPLENTE", "nunique", {"conta": "cliente"}),
            # O da filial no mês (o mesmo em todo título dela): somado uma
            # vez por filial/mês. Por cliente/RCA, o % é a parte dele no
            # faturamento da filial, como na controladoria.
            "faturamento_liquido": ("FATURAMENTO_LIQ", "sum", {"unico_por": ("FILIAL", "ANO", "MES")}),
            "valor_em_atraso": ("VALOR_EM_ATRASO", "sum"),
            "titulos_em_atraso": ("TITULO_EM_ATRASO", "sum"),
            "clientes_em_atraso": ("CLIENTE_EM_ATRASO", "nunique", {"conta": "cliente"}),
            # Agrupado (filial, cliente): o título mais atrasado.
            "dias_de_atraso": ("DIAS_DE_ATRASO", "max"),
            "clientes_em_risco_de_bloqueio": ("CLIENTE_EM_RISCO_DE_BLOQUEIO", "nunique", {"conta": "cliente"}),
            "dias_para_o_bloqueio": ("DIAS_PARA_O_BLOQUEIO", "min"),
        },
        "dimensoes": {
            "filial": "FILIAL", "estado": "ESTADO", "rca": "COD_RCA",
            "supervisor": "COD_SUPERVISOR", "mes": "MES", "ano": "ANO",
            "cliente": "CODCLI", "empresa": "EMPRESA",
        },
        "resolver_dimensao": {
            "filial": resolver_nome_filial,
            "estado": resolver_estado,
            "rca": resolver_codigos_rca,
            "supervisor": resolver_codigos_supervisor,
            "cliente": resolver_codigos_cliente,
            "empresa": resolver_empresas,
        },
        "rca_nome_mapa": construir_mapa_rca_nome,
        # Sem "rca_requer_meta_cadastrada": o título fica com o RCA mesmo
        # sem meta (ou desligado), e a soma dos RCAs fecha com a filial.
        "derivados": [
            {
                "nome": "percentual_inadimplencia",
                "formula": "calcular_inadimplencia",
                "campos": ("valor_inadimplente", "faturamento_liquido"),
            },
        ],
        "campo_principal": "valor_inadimplente",
        "unidade": "R$",
        "periodo_dos_campos": {
            "campos": ("valor_inadimplente", "titulos_inadimplentes", "clientes_inadimplentes", "percentual_inadimplencia"),
            "nome": "a inadimplência oficial",
            "aviso": "fechamento_da_inadimplencia",
            "descrever": descrever_fechamento,
            # Sem período, o oficial não é "todo o histórico".
            "sem_periodo": descrever_sem_periodo,
        },
        "como_ler": (
            "Mês/ano = do VENCIMENTO do título. Inadimplência OFICIAL (valor_inadimplente, "
            "titulos_inadimplentes, clientes_inadimplentes, "
            "percentual_inadimplencia) = o fechamento da controladoria: todo "
            "dia 10 fecha o mês de 2 meses antes (títulos vencidos nele e "
            "ainda em aberto no dia 10) — as datas vêm em "
            "fechamento_da_inadimplencia; mês ainda não fechado tem oficial "
            "zero: diga que ainda não fechou, não que não há inadimplência. "
            "percentual_inadimplencia = valor_inadimplente ÷ "
            "faturamento_liquido (o da filial nos meses fechados). EM ATRASO "
            "HOJE (valor_em_atraso, titulos_em_atraso, clientes_em_atraso, "
            "dias_de_atraso) = vencidos e não pagos agora, inclusive os dos "
            "meses ainda não fechados — é quem cobrar. Pergunta sem dizer "
            "qual ('quanto Timon tem de inadimplência?'): dê o oficial e o "
            "em atraso hoje, cada um com o nome. Risco de bloqueio: o "
            "cliente é bloqueado com 30 dias de atraso; em risco = o título "
            "mais atrasado dele tem de 20 a 29 dias (dias_para_o_bloqueio = "
            "quantos faltam)."
        ),
        "exibicao": {
            "valor_inadimplente": {"tipo": "moeda", "rotulo": "Inadimplência oficial", "palavras": ["inadimpl"]},
            "percentual_inadimplencia": {"tipo": "percentual", "rotulo": "% Inadimplência", "palavras": ["inadimpl", "%", "percent"]},
            "titulos_inadimplentes": {"tipo": "texto", "rotulo": "Títulos (oficial)", "palavras": ["título", "titulo"]},
            "clientes_inadimplentes": {"tipo": "texto", "rotulo": "Clientes (oficial)", "palavras": ["inadimplentes"]},
            "faturamento_liquido": {"tipo": "moeda", "rotulo": "Faturamento Líquido", "palavras": ["fatur"]},
            "valor_em_atraso": {"tipo": "moeda", "rotulo": "Em atraso hoje", "palavras": ["atraso", "atrasad", "devend", "deve", "cobr"]},
            "titulos_em_atraso": {"tipo": "texto", "rotulo": "Títulos em atraso", "palavras": ["título", "titulo"]},
            "clientes_em_atraso": {"tipo": "texto", "rotulo": "Clientes em atraso", "palavras": ["clientes em atraso", "clientes devendo"]},
            "dias_de_atraso": {"tipo": "texto", "rotulo": "Dias de atraso", "palavras": ["dias"]},
            "clientes_em_risco_de_bloqueio": {"tipo": "texto", "rotulo": "Em risco de bloqueio", "palavras": ["bloque"]},
            "dias_para_o_bloqueio": {"tipo": "texto", "rotulo": "Dias para o bloqueio", "palavras": ["bloque"]},
        },
    },
}

# Clientes ativos, em risco, inativos, novos e recuperados (regras em
# core/repositories/situacao_cliente_repository.py). Cada campo conta os
# CLIENTES diferentes ("nunique"). Ativos/em risco/inativos são uma FOTO
# ("foto_por"): num período de vários meses vale o último (no mês atual,
# hoje); novos e recuperados juntam o período todo.
_FOTO_MENSAL = {"foto_por": ("ANO", "MES")}
# "conta": o que o campo conta — agrupado pelo próprio cliente, cada um
# "tem" 0 ou 1, e ordenar por isso não responde nada (ver
# orquestrador._sem_ordem_por_contagem).
_CONTA_CLIENTE = {"conta": "cliente"}
_FOTO_E_CONTA = {**_FOTO_MENSAL, **_CONTA_CLIENTE}

INDICADORES["clientes"] = {
    "carregar": carregar_situacao_clientes,
    "granularidade_periodo": "mensal",
    # Também "hoje", "ontem", "semana passada" ou datas: a situação no
    # último dia; novos, recuperados e frequência só desses dias.
    "aceita_dias": True,
    # Sem período: a situação de hoje.
    "periodo_padrao": "mes_atual",
    "campos": {
        "clientes_ativos": ("CLIENTE_ATIVO", "nunique", _FOTO_E_CONTA),
        "clientes_em_risco": ("CLIENTE_EM_RISCO", "nunique", _FOTO_E_CONTA),
        # Inativos = de 90 dias a 1 ano; os parados há mais tempo vêm à parte.
        "clientes_inativos": ("CLIENTE_INATIVO", "nunique", _FOTO_E_CONTA),
        "clientes_parados_ha_mais_de_1_ano": ("CLIENTE_PARADO_HA_MAIS_DE_1_ANO", "nunique", _FOTO_E_CONTA),
        # Dos ativos, os que só compraram em outra filial / com outro RCA
        # nos últimos 90 dias (a resposta avisa). Só numa consulta por
        # filial / por RCA ("so_com").
        "ativos_so_em_outra_filial": ("CLIENTE_SO_OUTRA_FILIAL", "nunique", {**_FOTO_E_CONTA, "so_com": "filial"}),
        "ativos_so_com_outro_rca": ("CLIENTE_SO_OUTRO_RCA", "nunique", {**_FOTO_E_CONTA, "so_com": "rca"}),
        "clientes_novos": ("CLIENTE_NOVO", "nunique", _CONTA_CLIENTE),
        "clientes_recuperados": ("CLIENTE_RECUPERADO", "nunique", _CONTA_CLIENTE),
        # Dias desde a última compra, em qualquer filial. Agrupado (empresa,
        # filial), vale o menor: a compra mais recente entre as lojas.
        "dias_sem_comprar": ("DIAS_SEM_COMPRAR", "min", _FOTO_MENSAL),
        # Só as compras na filial — numa consulta por filial.
        "dias_sem_comprar_na_filial": (
            "DIAS_SEM_COMPRAR_NA_FILIAL", "min", {**_FOTO_MENSAL, "so_com": "filial"},
        ),
        # O maior tempo que o cliente ficou parado antes de voltar a comprar
        # no período (0 = não voltou): "ficou 5 meses parado e voltou".
        "dias_parado_antes_de_voltar": ("DIAS_PARADO_ANTES_DE_VOLTAR", "max"),
        # Quantas vezes o cliente comprou no período e a média por mês.
        # Agrupado (filial): a média dos clientes que compraram, cada um uma
        # vez. Da empresa: os dias em que qualquer loja dela comprou.
        "frequencia_de_compra": (
            "FREQUENCIA_DE_COMPRA", "mean",
            {**_FOTO_MENSAL, "unico_por": ("CODCLI",), "coluna_com": ("empresa", "FREQUENCIA_DA_EMPRESA")},
        ),
        "compras_por_mes": (
            "COMPRAS_POR_MES", "mean",
            {**_FOTO_MENSAL, "unico_por": ("CODCLI",), "coluna_com": ("empresa", "COMPRAS_POR_MES_DA_EMPRESA")},
        ),
        # A mesma conta só com as compras na filial — numa consulta por filial.
        "frequencia_na_filial": (
            "FREQUENCIA_NA_FILIAL", "mean",
            {
                **_FOTO_MENSAL, "unico_por": ("CODCLI", "CODFILIAL"), "so_com": "filial",
                "coluna_com": ("empresa", "FREQUENCIA_DA_EMPRESA_NA_FILIAL"),
            },
        ),
        "compras_por_mes_na_filial": (
            "COMPRAS_POR_MES_NA_FILIAL", "mean",
            {
                **_FOTO_MENSAL, "unico_por": ("CODCLI", "CODFILIAL"), "so_com": "filial",
                "coluna_com": ("empresa", "COMPRAS_POR_MES_DA_EMPRESA_NA_FILIAL"),
            },
        ),
    },
    # Lista de clientes: quantos de TODA a lista em cada situação e, sem
    # ordem pedida, os que pararam há menos tempo primeiro (ver
    # orquestrador._lista_de_itens).
    "lista_de_itens": {
        "dimensao": "cliente",
        "resumir_por": "situacao",
        "ordem": ("dias_sem_comprar", "asc"),
    },
    "dimensoes": {
        "filial": "FILIAL", "estado": "ESTADO", "rca": "COD_RCA",
        "supervisor": "COD_SUPERVISOR", "mes": "MES", "ano": "ANO",
        "cliente": "CODCLI", "empresa": "EMPRESA", "dia": "DATA_DA_FOTO",
    },
    "resolver_dimensao": {
        "filial": resolver_nome_filial,
        "estado": resolver_estado,
        "rca": resolver_codigos_rca,
        "supervisor": resolver_codigos_supervisor,
        "cliente": resolver_codigos_cliente,
        "empresa": resolver_empresas,
    },
    "rca_nome_mapa": construir_mapa_rca_nome,
    "rca_requer_meta_cadastrada": True,
    "campo_principal": "clientes_ativos",
    "unidade": "clientes",
    # A frequência tem período próprio (sem período: o ano atual): as datas
    # vão prontas pra resposta (ver orquestrador._avisos_para_a_ia).
    "periodo_dos_campos": {
        "campos": ("frequencia_de_compra", "compras_por_mes", "frequencia_na_filial", "compras_por_mes_na_filial"),
        "nome": "a frequência de compra",
        "aviso": "periodo_da_frequencia",
        "descrever": periodo_da_frequencia,
    },
    # Vai junto com o resultado pra quem escreve a resposta (ver
    # orquestrador._avisos_para_a_ia).
    "como_ler": (
        "Ativo = comprou há menos de 90 dias (em risco = 60 a 89 dias, também "
        "ativo). Inativo = de 90 dias a 1 ano sem comprar: os que dá pra "
        "recuperar. Ao falar de inativos, diga TAMBÉM, numa frase à parte, os "
        "parados há mais de 1 ano (clientes_parados_ha_mais_de_1_ano) — ex: "
        "'Timon tem N clientes inativos (parados de 90 dias a 1 ano), os "
        "com mais chance de voltar. Além deles, M estão parados há mais "
        "de 1 ano.' Se vier ativos_so_em_outra_filial (ou "
        "ativos_so_com_outro_rca) maior que zero, diga quantos dos ativos só "
        "compraram em outra filial (com outro RCA) nos últimos 90 dias. "
        "Frequência de compra = quantas vezes o cliente comprou no período "
        "pedido (várias notas no mesmo dia = 1 vez; um ano: de janeiro até o "
        "fim dele, ou até hoje no ano atual; um mês passado: só ele; sem "
        "período ou no mês atual: o ano atual até hoje) — as datas vêm "
        "prontas em periodo_da_frequencia — e compras_por_mes, a média por "
        "mês. Mais vezes = compra com mais frequência. De uma empresa: os "
        "dias em que qualquer loja dela comprou. Agrupada por filial, é a "
        "média por cliente que comprou no período. Numa "
        "consulta por filial vêm também frequencia_na_filial, "
        "compras_por_mes_na_filial e dias_sem_comprar_na_filial (só as "
        "compras naquela filial). Responda a frequência assim (este formato "
        "já diz o período, mesmo sem período na pergunta): 'No período de "
        "<periodo_da_frequencia>, o cliente <nome> comprou N vezes (média "
        "de X por mês). Está há M dias sem comprar. Se preferir, você pode "
        "consultar outro período.' Por filial: 'o cliente <nome> comprou N "
        "vezes em <filial> (X por mês; em todas as filiais, N2 vezes, Y por "
        "mês). Está há M dias sem comprar em <filial> (em todas as filiais, "
        "há Z dias).' — os dias sem comprar vêm SEMPRE junto, pra mostrar "
        "quem está atrasado em relação ao costume. A última compra traz data e filial e, desde 2025, o "
        "valor (o que o cliente comprou, venda bruta), a(s) nota(s), o(s) "
        "pedido(s) e o RCA — várias notas no mesmo dia são uma compra só. "
        "Os dados começam em 2020."
    ),
    "exibicao": {
        "clientes_ativos": {"tipo": "texto", "rotulo": "Clientes Ativos", "sempre": True},
        "clientes_em_risco": {"tipo": "texto", "rotulo": "Em Risco de Perda", "palavras": ["risco", "perd"]},
        "clientes_inativos": {"tipo": "texto", "rotulo": "Inativos até 1 ano", "palavras": ["inativ"]},
        "clientes_parados_ha_mais_de_1_ano": {"tipo": "texto", "rotulo": "Parados há mais de 1 ano", "palavras": ["inativ", "parad", "mais de 1 ano", "mais de um ano"]},
        "clientes_novos": {"tipo": "texto", "rotulo": "Novos", "palavras": ["novo"]},
        "clientes_recuperados": {"tipo": "texto", "rotulo": "Recuperados", "palavras": ["recuper"]},
        "ativos_so_em_outra_filial": {"tipo": "texto", "rotulo": "Ativos só por outra filial", "palavras": ["outra filia"]},
        "ativos_so_com_outro_rca": {"tipo": "texto", "rotulo": "Ativos só por outro RCA", "palavras": ["outro rca", "outro vendedor"]},
        "dias_sem_comprar": {"tipo": "texto", "rotulo": "Dias sem comprar", "palavras": ["dias sem", "sem comprar"]},
        "dias_sem_comprar_na_filial": {"tipo": "texto", "rotulo": "Dias sem comprar, na filial", "palavras": ["dias sem", "sem comprar", "não compra"]},
        "frequencia_na_filial": {"tipo": "texto", "rotulo": "Compras no período, na filial", "palavras": ["frequ", "vezes"]},
        "compras_por_mes_na_filial": {"tipo": "texto", "rotulo": "Compras por mês, na filial", "palavras": ["frequ", "por mês"]},
        "frequencia_de_compra": {"tipo": "texto", "rotulo": "Compras no período, todas as filiais", "palavras": ["frequ", "vezes"]},
        "compras_por_mes": {"tipo": "texto", "rotulo": "Compras por mês, todas as filiais", "palavras": ["frequ", "por mês"]},
        "dias_parado_antes_de_voltar": {"tipo": "texto", "rotulo": "Dias parado antes de voltar", "palavras": ["voltou", "voltaram", "volta a comprar", "voltar a comprar"]},
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

        campos = ", ".join([
            *definicao["campos"],
            *(derivado["nome"] for derivado in definicao.get("derivados", [])),
        ])
        dimensoes = ", ".join(definicao["dimensoes"])

        linhas.append(
            f"  * {nome} ({definicao['unidade']}) — período "
            f"{definicao['granularidade_periodo']}"
            f"{' (também dias: hoje, ontem, semana, datas)' if definicao.get('aceita_dias') else ''}; campos: "
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
            # Diferença entre dois % é em pontos percentuais (3,04% → 5,36%
            # = +2,32 p.p.), não em %.
            "percentual": "pontos_percentuais_com_sinal", "texto": "numero_com_sinal",
            "moeda": "moeda_com_sinal",
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
