"""
Motor de dados genérico — busca, filtra, agrupa e aplica fórmulas
sobre qualquer indicador registrado em catalogo.py, sem precisar de
uma função Python nova por combinação de pergunta.

Fluxo de executar_consulta(): valida a consulta contra o catálogo →
busca os dados brutos (DataFrame) do indicador → filtra → agrupa/soma
→ aplica fórmulas derivadas (motor_metricas.py) → aplica filtros sobre
a métrica já calculada (ex: "só quem bateu a meta") → devolve um dict
no mesmo formato que as ferramentas antigas já usam
({"encontrado", "resultados", ...}).

Generaliza o padrão de groupby().agg() que antes era repetido em um
arquivo de queries por indicador — um indicador novo com fonte real
só precisa de uma entrada em catalogo.py, não de um arquivo de
queries dedicado.
"""
import operator
from datetime import date, timedelta

import pandas as pd

from src import catalogo, motor_metricas
from src.exceptions import ConsultaInvalida
from src.variacao_utils import (
    calcular_diferenca_percentual,
    calcular_variacao_sequencial,
)

_ORDEM_RESOLUCAO_DIMENSOES = ("filial", "rca", "supervisor")

_OPERADORES = {
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
    "==": operator.eq,
    "!=": operator.ne,
}


def validar_consulta(consulta: dict) -> None:
    """
    Rejeita indicador, dimensão ou período fora do catálogo,
    levantando ConsultaInvalida com uma mensagem clara.
    """
    indicador = consulta.get("indicador")

    if not catalogo.indicador_existe(indicador):
        raise ConsultaInvalida(
            f"O indicador '{indicador}' não existe no catálogo."
        )

    for dimensao in consulta.get("agrupar_por") or []:
        if not catalogo.dimensao_permitida(indicador, dimensao):
            raise ConsultaInvalida(
                f"A dimensão '{dimensao}' não é permitida para o "
                f"indicador '{indicador}'."
            )

    for dimensao in (consulta.get("filtros") or {}):
        if not catalogo.dimensao_permitida(indicador, dimensao):
            raise ConsultaInvalida(
                f"O filtro '{dimensao}' não é permitido para o "
                f"indicador '{indicador}'."
            )

    for campo_periodo in ("periodo", "comparar_com"):
        valor_periodo = consulta.get(campo_periodo)

        if valor_periodo and valor_periodo not in catalogo.PERIODOS_VALIDOS:
            raise ConsultaInvalida(
                f"O período '{valor_periodo}' não é reconhecido."
            )

    ordenar_por = consulta.get("ordenar_por")

    if ordenar_por:
        indicador_def = catalogo.INDICADORES[indicador]
        campos_base = set(indicador_def.get("campos", {}))
        campos_validos = campos_base | {
            derivado["nome"] for derivado in indicador_def.get("derivados", [])
        }

        # "comparar_com" cria, em tempo de execução, 3 campos extras
        # por campo base ("{campo}_anterior", "diferenca_{campo}",
        # "percentual_{campo}") — precisam contar como válidos aqui
        # também, senão "ordenar_por" nunca consegue ordenar pelo
        # crescimento calculado.
        if consulta.get("comparar_com"):
            for campo in campos_base:
                campos_validos |= {
                    f"{campo}_anterior",
                    f"diferenca_{campo}",
                    f"percentual_{campo}",
                }

        campo_ordenacao = ordenar_por.get("campo")

        if campo_ordenacao not in campos_validos:
            raise ConsultaInvalida(
                f"O campo '{campo_ordenacao}' não pode ser usado em "
                f"'ordenar_por' para o indicador '{indicador}'."
            )


def resolver_periodo(
    periodo: str,
    personalizado: dict | None,
    granularidade: str,
) -> dict:
    """
    Traduz o vocabulário de período do catálogo (mes_atual, ano_atual,
    mesmo_mes_ano_anterior, personalizado...) em filtros concretos —
    meses/anos (indicadores "mensais") ou um intervalo de datas
    (indicadores "diarios"), conforme a granularidade do indicador.
    """
    hoje = date.today()

    if periodo == "personalizado":
        if not personalizado:
            raise ConsultaInvalida(
                "periodo_personalizado é obrigatório quando "
                "periodo='personalizado'."
            )

        if granularidade == "mensal":
            filtro = {}

            if personalizado.get("meses"):
                filtro["mes"] = personalizado["meses"]

            if personalizado.get("anos"):
                filtro["ano"] = personalizado["anos"]

            return filtro

        return {
            "dia": {
                "data_inicial": personalizado["data_inicial"],
                "data_final": personalizado["data_final"],
            }
        }

    if granularidade == "mensal":
        if periodo == "mes_atual":
            return {"mes": [hoje.month], "ano": [hoje.year]}

        if periodo == "ano_atual":
            return {"ano": [hoje.year]}

        if periodo == "mes_anterior":
            mes_anterior = hoje.month - 1 or 12
            ano_do_mes_anterior = (
                hoje.year if hoje.month > 1 else hoje.year - 1
            )
            return {"mes": [mes_anterior], "ano": [ano_do_mes_anterior]}

        if periodo == "mesmo_mes_ano_anterior":
            return {"mes": [hoje.month], "ano": [hoje.year - 1]}

        raise ConsultaInvalida(
            f"O período '{periodo}' não é suportado para indicadores "
            "mensais."
        )

    if periodo == "hoje":
        return {
            "dia": {
                "data_inicial": hoje.isoformat(),
                "data_final": hoje.isoformat(),
            }
        }

    if periodo == "ontem":
        ontem = hoje - timedelta(days=1)
        return {
            "dia": {
                "data_inicial": ontem.isoformat(),
                "data_final": ontem.isoformat(),
            }
        }

    if periodo == "semana_atual":
        inicio_semana = hoje - timedelta(days=hoje.weekday())
        return {
            "dia": {
                "data_inicial": inicio_semana.isoformat(),
                "data_final": hoje.isoformat(),
            }
        }

    if periodo == "mes_atual":
        return {
            "dia": {
                "data_inicial": hoje.replace(day=1).isoformat(),
                "data_final": hoje.isoformat(),
            }
        }

    if periodo == "ano_atual":
        return {
            "dia": {
                "data_inicial": hoje.replace(month=1, day=1).isoformat(),
                "data_final": hoje.isoformat(),
            }
        }

    raise ConsultaInvalida(
        f"O período '{periodo}' não é suportado para indicadores diários."
    )


def _aplicar_filtros(
    dados: pd.DataFrame, indicador_def: dict, filtros: dict
) -> tuple[pd.DataFrame, dict]:
    dimensoes = indicador_def["dimensoes"]
    resolvedores = indicador_def.get("resolver_dimensao", {})
    filtros_resolvidos: dict[str, list] = {}

    dimensoes_ordenadas = [
        dimensao
        for dimensao in _ORDEM_RESOLUCAO_DIMENSOES
        if dimensao in filtros
    ] + [
        dimensao
        for dimensao in filtros
        if dimensao not in _ORDEM_RESOLUCAO_DIMENSOES
    ]

    for dimensao in dimensoes_ordenadas:
        valor = filtros[dimensao]
        coluna = dimensoes.get(dimensao)

        if coluna is None:
            continue

        if dimensao == "dia" and isinstance(valor, dict):
            dados = dados[
                (dados[coluna] >= pd.to_datetime(valor["data_inicial"]))
                & (dados[coluna] <= pd.to_datetime(valor["data_final"]))
            ]
            continue

        valores = valor if isinstance(valor, list) else [valor]
        resolvedor = resolvedores.get(dimensao)

        if resolvedor:
            valores_resolvidos = []

            for item in valores:
                if dimensao in ("rca", "supervisor"):
                    encontrados = resolvedor(
                        item, filiais=filtros_resolvidos.get("filial")
                    )
                else:
                    encontrados = [resolvedor(item)]

                for encontrado in encontrados:
                    if encontrado not in valores_resolvidos:
                        valores_resolvidos.append(encontrado)

            valores = valores_resolvidos

        filtros_resolvidos[dimensao] = valores
        dados = dados[dados[coluna].isin(valores)]

    return dados, filtros_resolvidos


def _rcas_com_meta_cadastrada(
    filiais: list[str] | None, anos: list[int] | None
) -> set[int]:
    """
    "RCA de uma filial" é, no negócio, quem tem meta cadastrada ali —
    não qualquer código que apareceu na base (contas genéricas/
    contábeis também vendem, mas não são vendedores de verdade). Essa
    definição usa sempre a base de metas como referência, mesmo
    quando o indicador consultado é outro (faturamento) — é uma regra
    compartilhada entre indicadores, não específica de um.
    """
    dados_meta = catalogo.INDICADORES["meta"]["carregar"]()

    if filiais:
        dados_meta = dados_meta[dados_meta["FILIAL"].isin(filiais)]

    if anos:
        dados_meta = dados_meta[dados_meta["ANO"].isin(anos)]

    metas_por_rca = dados_meta.groupby("COD_RCA")["VALOR_META"].sum()

    return set(metas_por_rca[metas_por_rca > 0].index.astype(int))


def buscar_dados_brutos(
    indicador_def: dict,
    agrupar_por: list[str],
    filtros: dict,
    rcas_validos: set[int] | None = None,
) -> tuple[pd.DataFrame, set[int] | None]:
    """
    Carrega o DataFrame real do indicador (via indicador_def["carregar"])
    e aplica os filtros. Levanta ConsultaInvalida se o indicador ainda
    não tiver fonte de dados conectada.

    Quando a consulta agrupa por "rca" sem o usuário ter pedido RCAs
    específicos, e o indicador marca "rca_requer_meta_cadastrada",
    restringe automaticamente aos RCAs com meta cadastrada — mesma
    regra que as ferramentas antigas já aplicavam por padrão.

    `rcas_validos`, quando informado, é usado em vez de calcular de
    novo — necessário quando essa função é chamada duas vezes pra
    períodos diferentes (comparar_com): o conjunto de RCAs "válidos"
    precisa ser o MESMO nas duas chamadas (definido pelo período
    principal), senão um RCA que tem meta este ano mas não tinha no
    ano anterior perderia o histórico do ano anterior inteiro (não só
    a meta, o realizado também), estragando o cálculo de crescimento.
    """
    carregar = indicador_def.get("carregar")

    if (
        ("forma_pagamento" in agrupar_por or "forma_pagamento" in filtros)
        and indicador_def.get("carregar_forma_pagamento")
    ):
        carregar = indicador_def["carregar_forma_pagamento"]

    if carregar is None:
        raise ConsultaInvalida(
            "Esse indicador ainda não está conectado a uma fonte de "
            "dados real — não é possível buscar o valor pedido."
        )

    dados = carregar()
    dados, filtros_resolvidos = _aplicar_filtros(dados, indicador_def, filtros)

    if (
        "rca" in agrupar_por
        and "rca" not in filtros
        and indicador_def.get("rca_requer_meta_cadastrada")
    ):
        if rcas_validos is None:
            rcas_validos = _rcas_com_meta_cadastrada(
                filtros_resolvidos.get("filial"), filtros_resolvidos.get("ano")
            )

        coluna_rca = indicador_def["dimensoes"]["rca"]
        dados = dados[dados[coluna_rca].isin(rcas_validos)]

    return dados, rcas_validos


def _desempacotar_campo(especificacao) -> tuple[str, str, dict]:
    """
    Um campo no catálogo pode ser (coluna, agregacao) — o caso comum —
    ou (coluna, agregacao, opcoes), quando precisa de algo além de
    somar/agregar direto. Hoje a única opção é "unico_por": um valor
    que se repete em várias linhas (ex: a meta de tonelada por FILIAL
    aparece copiada em toda linha de RCA daquele filial/mês) — antes
    de agregar, descarta as linhas repetidas, mantendo uma só por
    combinação de colunas informada, pra não somar o mesmo valor mais
    de uma vez.
    """
    if len(especificacao) == 3:
        coluna, agregacao, opcoes = especificacao
    else:
        coluna, agregacao = especificacao
        opcoes = {}

    return coluna, agregacao, opcoes


def _particionar_campos_por_dedup(campos: dict) -> list[tuple[tuple | None, dict]]:
    """
    Agrupa os campos por chave de "unico_por" — campos sem essa opção
    formam um grupo só (chave None), campos com a mesma chave formam
    outro grupo. Cada grupo é agregado separadamente (usando a fonte
    de dados deduplicada quando aplicável) e depois juntado de volta.
    """
    grupos: dict[tuple | None, dict] = {}

    for nome_campo, especificacao in campos.items():
        coluna, agregacao, opcoes = _desempacotar_campo(especificacao)
        chave = opcoes.get("unico_por")
        grupos.setdefault(chave, {})[nome_campo] = (coluna, agregacao)

    return list(grupos.items())


def _aplicar_agrupamento(
    dados: pd.DataFrame, indicador_def: dict, agrupar_por: list[str]
) -> list[dict]:
    """
    Sempre devolve uma LISTA — mesmo sem agrupamento (nesse caso, uma
    lista com um único item, o total agregado). Isso evita ter um
    formato "dict solto" só pra esse caso, e mantém o resto do motor
    (comparação, derivados, filtros calculados) trabalhando com um
    único formato, sem caso especial.
    """
    campos = indicador_def["campos"]
    grupos_de_campos = _particionar_campos_por_dedup(campos)

    if not agrupar_por:
        item = {}

        for chave_dedup, campos_do_grupo in grupos_de_campos:
            dados_do_grupo = (
                dados.drop_duplicates(subset=list(chave_dedup))
                if chave_dedup else dados
            )

            for nome_campo, (coluna, agregacao) in campos_do_grupo.items():
                valor = getattr(dados_do_grupo[coluna], agregacao)()
                item[nome_campo] = round(float(valor), 2)

        return [item]

    dimensoes = indicador_def["dimensoes"]
    colunas_agrupamento = [dimensoes[dimensao] for dimensao in agrupar_por]

    tabelas_agregadas = []

    for chave_dedup, campos_do_grupo in grupos_de_campos:
        if chave_dedup:
            # A duplicata só pode ser descartada DENTRO de cada grupo
            # da consulta, não no DataFrame inteiro — senão, ao
            # agrupar por uma dimensão que não faz parte da chave de
            # dedup (ex: "rca", quando a chave é filial/ano/mês), só
            # o primeiro item de cada combinação sobreviveria, e os
            # demais ficariam com o campo zerado.
            colunas_dedup = list(
                dict.fromkeys([*colunas_agrupamento, *chave_dedup])
            )
            dados_do_grupo = dados.drop_duplicates(subset=colunas_dedup)
        else:
            dados_do_grupo = dados

        tabelas_agregadas.append(
            dados_do_grupo
            .groupby(colunas_agrupamento, dropna=False)
            .agg(**campos_do_grupo)
        )

    agrupado = tabelas_agregadas[0]

    for tabela in tabelas_agregadas[1:]:
        agrupado = agrupado.join(tabela, how="outer")

    agrupado = agrupado.fillna(0).reset_index()

    resultados = []

    for _, linha in agrupado.iterrows():
        item = {}

        for dimensao, coluna in zip(agrupar_por, colunas_agrupamento):
            valor = linha[coluna]

            if dimensao in ("mes", "ano", "rca", "supervisor"):
                # "rca" é código numérico na maioria das bases, mas é
                # NOME (texto) na base de meta de tonelada — tenta
                # converter, e se não der, trata como texto mesmo.
                try:
                    valor = int(valor)
                except (TypeError, ValueError):
                    valor = str(valor)
            elif dimensao == "dia":
                valor = (
                    valor.strftime("%Y-%m-%d")
                    if hasattr(valor, "strftime")
                    else str(valor)
                )
            elif pd.isna(valor):
                valor = "Não informado"
            else:
                valor = str(valor)

            item[dimensao] = valor

        for nome_campo in campos:
            item[nome_campo] = round(float(linha[nome_campo]), 2)

        resultados.append(item)

    mapa_rca_nome_func = indicador_def.get("rca_nome_mapa")

    if "rca" in agrupar_por and mapa_rca_nome_func:
        mapa_rca_nome = mapa_rca_nome_func()

        for item in resultados:
            item["rca_nome"] = mapa_rca_nome.get(item["rca"])

    return resultados


def _consultar_periodo(
    indicador_def: dict,
    consulta: dict,
    periodo: str | None,
    periodo_personalizado: dict | None,
    agrupar_por: list[str],
    rcas_validos: set[int] | None = None,
) -> tuple[list[dict], set[int] | None]:
    filtros = dict(consulta.get("filtros") or {})

    if periodo == "ano_anterior_ao_filtro":
        # Não é um período "pronto" como os outros — pega o(s) ano(s)
        # que a própria consulta já filtrou e usa ano-1 de cada um.
        # Só faz sentido como "comparar_com" (a consulta original
        # precisa ter "ano" nos filtros).
        anos_atuais = filtros.get("ano")

        if not anos_atuais:
            raise ConsultaInvalida(
                "'ano_anterior_ao_filtro' exige que 'filtros' já "
                "tenha 'ano' definido."
            )

        filtros = {**filtros, "ano": [ano - 1 for ano in anos_atuais]}
    elif periodo:
        filtros.update(
            resolver_periodo(
                periodo,
                periodo_personalizado,
                indicador_def["granularidade_periodo"],
            )
        )

    dados, rcas_validos = buscar_dados_brutos(
        indicador_def, agrupar_por, filtros, rcas_validos
    )

    if dados.empty:
        return [], rcas_validos

    return _aplicar_agrupamento(dados, indicador_def, agrupar_por), rcas_validos


def _combinar_comparacao(
    atual: list[dict], anterior: list[dict], agrupar_por, campos
) -> list[dict]:
    """
    Junta o resultado do período atual com o do período de comparação
    (mesma chave de agrupamento), calculando diferença e percentual de
    cada campo numérico — mesma fórmula usada em toda variação
    "anterior" do projeto (variacao_utils.calcular_diferenca_percentual).
    """
    if not agrupar_por:
        if not atual:
            return []

        item_atual = atual[0]
        item_anterior = anterior[0] if anterior else {}
        combinado = dict(item_atual)

        for campo in campos:
            diferenca, percentual = calcular_diferenca_percentual(
                item_anterior.get(campo), item_atual.get(campo)
            )
            combinado[f"{campo}_anterior"] = item_anterior.get(campo)
            combinado[f"diferenca_{campo}"] = diferenca
            combinado[f"percentual_{campo}"] = percentual

        return [combinado]

    mapa_anterior = {
        tuple(item[dimensao] for dimensao in agrupar_por): item
        for item in anterior
    }

    resultados = []

    for item in atual:
        chave = tuple(item[dimensao] for dimensao in agrupar_por)
        item_anterior = mapa_anterior.get(chave, {})
        combinado = dict(item)

        for campo in campos:
            diferenca, percentual = calcular_diferenca_percentual(
                item_anterior.get(campo), item.get(campo)
            )
            combinado[f"{campo}_anterior"] = item_anterior.get(campo)
            combinado[f"diferenca_{campo}"] = diferenca
            combinado[f"percentual_{campo}"] = percentual

        resultados.append(combinado)

    return resultados


def _aplicar_variacao_temporal(
    resultado: list[dict],
    agrupar_por: list[str],
    indicador_def: dict,
    filtros: dict,
) -> list[dict]:
    """
    Quando a consulta agrupa por "mes" (com ou sem "ano"), preenche
    automaticamente a variação em relação ao período anterior — mesmo
    padrão já usado por NPS e Metas antes deste motor existir (veja
    variacao_utils.calcular_variacao_sequencial):
    - "mes" + "ano" agrupados, com 2+ anos filtrados: compara cada mês
      com o MESMO mês do ano anterior da lista (campos
      "{campo}_ano_anterior", "diferenca_ano_anterior",
      "percentual_ano_anterior").
    - só "mes" agrupado, com exatamente 1 ano filtrado: compara cada
      mês com o mês imediatamente anterior dentro do mesmo ano (campos
      "diferenca_mes_anterior", "percentual_mes_anterior").

    Usa o campo definido em indicador_def["campo_principal"] — o
    indicador que faz sentido acompanhar ao longo do tempo (ex:
    faturamento realizado, não a meta em si). Indicadores sem esse
    campo definido não recebem essa variação automática.
    """
    campo = indicador_def.get("campo_principal")

    if not campo or not resultado or "mes" not in agrupar_por:
        return resultado

    dimensoes_extras = [
        dimensao for dimensao in agrupar_por if dimensao not in ("mes", "ano")
    ]

    anos = filtros.get("ano")
    anos = anos if isinstance(anos, list) else None

    if "ano" in agrupar_por and anos and len(anos) >= 2:
        posicao_do_ano = {ano: indice for indice, ano in enumerate(anos)}

        calcular_variacao_sequencial(
            resultado,
            campo_valor=campo,
            sufixo="ano_anterior",
            chave_grupo=lambda item: (
                tuple(item[dimensao] for dimensao in dimensoes_extras),
                item["mes"],
            ),
            chave_ordem=lambda item: (
                tuple(item[dimensao] for dimensao in dimensoes_extras),
                item["mes"],
                posicao_do_ano.get(item["ano"], len(anos)),
            ),
            incluir_valor_anterior_como=f"{campo}_ano_anterior",
        )
        return resultado

    if "ano" not in agrupar_por and anos and len(anos) == 1:
        calcular_variacao_sequencial(
            resultado,
            campo_valor=campo,
            sufixo="mes_anterior",
            chave_grupo=lambda item: tuple(
                item[dimensao] for dimensao in dimensoes_extras
            ),
            chave_ordem=lambda item: (
                tuple(item[dimensao] for dimensao in dimensoes_extras),
                item["mes"],
            ),
        )

    return resultado


def _aplicar_necessidade_diaria(
    resultado: list[dict],
    agrupar_por: list[str],
    indicador_def: dict,
    filtros: dict,
) -> list[dict]:
    """
    Preenche "necessidade_diaria" (quanto falta vender por dia útil
    restante) quando a consulta é do indicador de meta, SEM
    agrupamento, e filtra exatamente um mês e um ano — e esse mês/ano
    é o atual (mesma regra da ferramenta antiga: só faz sentido pro
    mês corrente).
    """
    campo_faltante = indicador_def.get("necessidade_diaria_campo")

    if not campo_faltante or agrupar_por or not resultado:
        return resultado

    meses = filtros.get("mes")
    anos = filtros.get("ano")

    if not (isinstance(meses, list) and isinstance(anos, list)):
        return resultado

    if len(meses) != 1 or len(anos) != 1:
        return resultado

    dias_restantes = motor_metricas.calcular_dias_uteis_restantes(
        anos[0], meses[0]
    )

    if not dias_restantes:
        return resultado

    item = resultado[0]
    item["necessidade_diaria"] = motor_metricas.calcular_necessidade_diaria(
        item.get(campo_faltante), dias_restantes
    )

    return resultado


def _aplicar_derivados(resultado: list[dict], indicador_def: dict) -> list[dict]:
    derivados = indicador_def.get("derivados")

    if not derivados:
        return resultado

    def _computar(item):
        item = dict(item)

        for derivado in derivados:
            funcao = motor_metricas.FORMULAS[derivado["formula"]]
            argumentos = [item.get(campo) for campo in derivado["campos"]]
            item[derivado["nome"]] = funcao(*argumentos)

        return item

    return [_computar(item) for item in resultado]


def _aplicar_ordenacao(resultado: list[dict], ordenar_por: dict | None) -> list[dict]:
    """
    Ordena o resultado por um campo e, opcionalmente, corta pros N
    primeiros — usado pra "os N maiores/menores" ter uma resposta
    EXATA, calculada aqui, em vez de a IA precisar comparar os itens
    de uma lista grande "de olho" e arriscar escolher errado (o mesmo
    princípio de nunca deixar a IA calcular, aplicado à comparação).
    Itens sem valor no campo (None) são ignorados — não dá pra
    ordenar por um valor que não existe.
    """
    if not ordenar_por or not resultado:
        return resultado

    campo = ordenar_por["campo"]
    ordem = ordenar_por.get("ordem", "desc")
    limite = ordenar_por.get("limite")

    itens_validos = [item for item in resultado if item.get(campo) is not None]

    itens_ordenados = sorted(
        itens_validos, key=lambda item: item[campo], reverse=(ordem != "asc")
    )

    if limite:
        itens_ordenados = itens_ordenados[:limite]

    return itens_ordenados


def _aplicar_filtro_calculado(resultado: list[dict], filtro: dict) -> list[dict]:
    campo = filtro["campo"]
    operador_nome = filtro["operador"]
    valor_comparado = filtro["valor"]

    operador_funcao = _OPERADORES.get(operador_nome)

    if operador_funcao is None:
        raise ConsultaInvalida(
            f"Operador '{operador_nome}' não é suportado em "
            "filtros_calculados."
        )

    return [
        item
        for item in resultado
        if item.get(campo) is not None
        and operador_funcao(item[campo], valor_comparado)
    ]


def executar_consulta(consulta: dict) -> dict:
    """
    Ponto único de entrada do motor genérico: valida a consulta,
    busca os dados reais, agrupa, aplica fórmulas derivadas e filtros
    sobre a métrica já calculada, e devolve o resultado.

    Formato esperado de `consulta`:
    - indicador (obrigatório): nome do indicador no catálogo.
    - periodo (opcional): um dos catalogo.PERIODOS_VALIDOS.
    - periodo_personalizado (opcional): {"meses": [...], "anos": [...]}
      ou {"data_inicial": ..., "data_final": ...}, conforme a
      granularidade do indicador — usado quando periodo="personalizado".
    - filtros (opcional): {dimensao: valor ou lista de valores}.
    - agrupar_por (opcional): lista de dimensões.
    - comparar_com (opcional): outro período do catálogo — quando
      informado, o resultado ganha campo_anterior/diferenca_campo/
      percentual_campo pra cada campo numérico do indicador.
    - filtros_calculados (opcional): lista de
      {"campo": ..., "operador": ">="|"<="|">"|"<"|"=="|"!=", "valor": ...}
      aplicada sobre o resultado já agregado (ex: só quem bateu a meta).
    - ordenar_por (opcional): {"campo": ..., "ordem": "desc"|"asc"
      (padrão "desc"), "limite": N} — ordena o resultado por um campo
      e corta pros N primeiros, de forma exata. Use pra "os N
      maiores/menores" em vez de confiar na IA pra comparar uma lista
      grande de itens "de olho".
    """
    validar_consulta(consulta)

    indicador = consulta["indicador"]
    indicador_def = catalogo.INDICADORES[indicador]
    agrupar_por = consulta.get("agrupar_por") or []

    resultado, rcas_validos = _consultar_periodo(
        indicador_def,
        consulta,
        consulta.get("periodo"),
        consulta.get("periodo_personalizado"),
        agrupar_por,
    )

    comparar_com = consulta.get("comparar_com")

    if comparar_com:
        # Reaproveita o MESMO conjunto de RCAs válidos calculado pro
        # período principal — ver docstring de buscar_dados_brutos.
        resultado_comparacao, _ = _consultar_periodo(
            indicador_def, consulta, comparar_com, None, agrupar_por,
            rcas_validos=rcas_validos,
        )
        resultado = _combinar_comparacao(
            resultado,
            resultado_comparacao,
            agrupar_por,
            list(indicador_def["campos"]),
        )
    else:
        resultado = _aplicar_variacao_temporal(
            resultado, agrupar_por, indicador_def, consulta.get("filtros") or {}
        )

    resultado = _aplicar_derivados(resultado, indicador_def)

    if not comparar_com:
        resultado = _aplicar_necessidade_diaria(
            resultado, agrupar_por, indicador_def, consulta.get("filtros") or {}
        )

    for filtro_calculado in consulta.get("filtros_calculados") or []:
        resultado = _aplicar_filtro_calculado(resultado, filtro_calculado)

    resultado = _aplicar_ordenacao(resultado, consulta.get("ordenar_por"))

    return {
        "encontrado": bool(resultado),
        "indicador": indicador,
        "filtros_aplicados": consulta.get("filtros"),
        "agrupar_por": agrupar_por or None,
        "resultados": resultado,
    }
