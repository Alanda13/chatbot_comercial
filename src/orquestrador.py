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
import calendar
import operator
from datetime import date, timedelta

import pandas as pd

from src import catalogo, motor_metricas
from src.exceptions import ConsultaInvalida
from src.filiais import CODIGO_POR_NOME
from src.variacao_utils import (
    calcular_diferenca_percentual,
    calcular_variacao_sequencial,
)

_ORDEM_RESOLUCAO_DIMENSOES = ("filial", "rca", "supervisor")

# Dimensões em que os indicadores usam o MESMO valor nas bases (o nome
# padrão da filial, o mês, o ano) — só por elas dá pra juntar dois
# indicadores. "rca" fica de fora: faturamento usa o código e a meta de
# tonelada usa o nome, então a junção sairia vazia sem avisar.
_DIMENSOES_DE_CRUZAMENTO = ("filial", "estado", "mes", "ano")

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
    cruzar_com = consulta.get("cruzar_com") or []
    indicadores = [indicador, *cruzar_com]

    for nome in indicadores:
        if not catalogo.indicador_existe(nome):
            raise ConsultaInvalida(
                f"O indicador '{nome}' não existe no catálogo."
            )

    if cruzar_com:
        _validar_cruzamento(indicadores, consulta.get("agrupar_por") or [])

    # Cada indicador da consulta precisa aceitar todas as dimensões e
    # filtros — um filtro que um deles não tem seria ignorado em silêncio.
    for nome in indicadores:
        for dimensao in consulta.get("agrupar_por") or []:
            if not catalogo.dimensao_permitida(nome, dimensao):
                raise ConsultaInvalida(
                    f"A dimensão '{dimensao}' não é permitida para o "
                    f"indicador '{nome}'."
                )

        for dimensao in (consulta.get("filtros") or {}):
            if not catalogo.dimensao_permitida(nome, dimensao):
                raise ConsultaInvalida(
                    f"O filtro '{dimensao}' não é permitido para o "
                    f"indicador '{nome}'."
                )

    for campo_periodo in ("periodo", "comparar_com"):
        valor_periodo = consulta.get(campo_periodo)

        if valor_periodo and valor_periodo not in catalogo.PERIODOS_VALIDOS:
            raise ConsultaInvalida(
                f"O período '{valor_periodo}' não é reconhecido."
            )

    comparar_filtros = consulta.get("comparar_filtros")

    if comparar_filtros:
        if not isinstance(comparar_filtros, dict):
            raise ConsultaInvalida("'comparar_filtros' deve ser um dicionário.")

        for dimensao in comparar_filtros:
            if dimensao in (consulta.get("agrupar_por") or []):
                raise ConsultaInvalida(
                    f"A dimensão '{dimensao}' está em 'comparar_filtros' e "
                    "também em 'agrupar_por' — os dois lados não se casariam. "
                    "Tire-a do agrupamento."
                )

            for nome in indicadores:
                if not catalogo.dimensao_permitida(nome, dimensao):
                    raise ConsultaInvalida(
                        f"O filtro '{dimensao}' não é permitido para o "
                        f"indicador '{nome}'."
                    )

    colunas = consulta.get("colunas")

    if colunas:
        invalidas = [
            coluna for coluna in colunas
            if coluna not in _campos_da_consulta(indicadores)
            and coluna != "necessidade_diaria"
        ]

        if invalidas:
            raise ConsultaInvalida(
                f"A(s) coluna(s) {', '.join(map(str, invalidas))} não "
                "existe(m) para essa consulta."
            )

    ordenar_por = consulta.get("ordenar_por")

    if ordenar_por:
        campos_validos = set(_campos_da_consulta(indicadores))

        # "comparar_com" cria, em tempo de execução, 3 campos extras
        # por campo base ("{campo}_anterior", "diferenca_{campo}",
        # "percentual_{campo}") — precisam contar como válidos aqui
        # também, senão "ordenar_por" nunca consegue ordenar pelo
        # crescimento calculado.
        if consulta.get("comparar_com"):
            for campo in list(campos_validos):
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


def _campos_do_indicador(indicador_def: dict) -> list[str]:
    """Campos somados + campos calculados (derivados) de um indicador."""
    return [
        *indicador_def["campos"],
        *(derivado["nome"] for derivado in indicador_def.get("derivados", [])),
    ]


def _derivados_do_cruzamento(indicadores: list[str]) -> list[dict]:
    """Derivados que dependem de dois indicadores (catalogo.CRUZAMENTOS)
    e cujos indicadores estão TODOS na consulta."""
    return [
        derivado
        for cruzamento in catalogo.CRUZAMENTOS
        if set(cruzamento["indicadores"]) <= set(indicadores)
        for derivado in cruzamento["derivados"]
    ]


def _campos_da_consulta(indicadores: list[str]) -> list[str]:
    """Todos os campos que a consulta produz: os de cada indicador mais
    os derivados do cruzamento."""
    return [
        *(
            campo
            for nome in indicadores
            for campo in _campos_do_indicador(catalogo.INDICADORES[nome])
        ),
        *(derivado["nome"] for derivado in _derivados_do_cruzamento(indicadores)),
    ]


def _linhas_da_tabela(
    resultado: list[dict], colunas: list[str], rotulos: dict | None = None
) -> list[dict]:
    """
    As linhas que vão pra tabela da tela: só a identificação (filial, mês,
    ...), os campos que a pergunta pediu ("colunas") e a comparação deles
    (anterior/diferença/variação). O resultado completo continua indo pra
    IA; só a TABELA é enxuta. "_colunas_pedidas" avisa a tela de que a
    escolha foi feita aqui (veja app.preparar_tabela); "_rotulos", quando
    há, troca o título de colunas (ex: os nomes das duas filiais).
    """
    comparacoes = {
        nome
        for coluna in colunas
        for nome in (
            f"{coluna}_anterior", f"diferenca_{coluna}", f"percentual_{coluna}"
        )
    }
    fixas = {*catalogo.DIMENSOES_VALIDAS, "rca_nome"}

    def manter(chave: str) -> bool:
        return (
            chave in fixas
            or chave in colunas
            or chave in comparacoes
            or chave.endswith(("_mes_anterior", "_ano_anterior"))
        )

    return [
        {
            **{chave: valor for chave, valor in linha.items() if manter(chave)},
            "_colunas_pedidas": colunas,
            **({"_rotulos": rotulos} if rotulos else {}),
        }
        for linha in resultado
    ]


def _nome_do_lado(indicador_def: dict, filtros: dict, dimensoes: list[str]) -> str:
    """Nome legível de um lado da comparação entre itens (ex: "TIMON")."""
    partes = []

    for dimensao in dimensoes:
        valores = filtros.get(dimensao)

        if not valores:
            partes.append("GERAL")
            continue

        resolvedor = indicador_def.get("resolver_dimensao", {}).get(dimensao)

        for valor in valores if isinstance(valores, list) else [valores]:
            try:
                nome = (
                    resolvedor(valor)
                    if resolvedor and dimensao in ("filial", "estado")
                    else valor
                )
            except ValueError:
                nome = valor

            partes.append(str(nome))

    return " + ".join(partes)


def _normalizar_comparacoes(consulta: dict) -> dict:
    """
    "comparar_com" (período contra período) e "comparar_filtros" (item
    contra item) juntos têm uma leitura só: cada item, período contra
    período — ex: "Timon e Lourival, 1º semestre de 2025 contra o de
    2024". Vira uma consulta agrupada por aquela dimensão (com os dois
    itens nos filtros) e só "comparar_com". Assim um deslize da IA em
    misturar os dois não vira um erro pro usuário.
    """
    comparar_filtros = consulta.get("comparar_filtros")

    if not (comparar_filtros and consulta.get("comparar_com")):
        return consulta

    filtros = dict(consulta.get("filtros") or {})
    agrupar_por = list(consulta.get("agrupar_por") or [])

    for dimensao, valores in comparar_filtros.items():
        if dimensao in filtros:
            juntos = [
                *(filtros[dimensao] if isinstance(filtros[dimensao], list) else [filtros[dimensao]]),
                *(valores if isinstance(valores, list) else [valores]),
            ]
            filtros[dimensao] = list(dict.fromkeys(juntos))

        if dimensao not in agrupar_por:
            agrupar_por.append(dimensao)

    return {
        **consulta, "filtros": filtros, "agrupar_por": agrupar_por,
        "comparar_filtros": None,
    }


def _validar_cruzamento(indicadores: list[str], agrupar_por: list[str]) -> None:
    if len(set(indicadores)) != len(indicadores):
        raise ConsultaInvalida(
            "'cruzar_com' não pode repetir o indicador da consulta."
        )

    for dimensao in agrupar_por:
        if dimensao not in _DIMENSOES_DE_CRUZAMENTO:
            raise ConsultaInvalida(
                "Só é possível cruzar indicadores agrupando por "
                f"{', '.join(_DIMENSOES_DE_CRUZAMENTO)} — a dimensão "
                f"'{dimensao}' não tem o mesmo valor em todas as bases."
            )

    vistos: set[str] = set()

    for nome in indicadores:
        campos = set(_campos_do_indicador(catalogo.INDICADORES[nome]))
        repetidos = vistos & campos

        if repetidos:
            raise ConsultaInvalida(
                "Os indicadores cruzados têm campos com o mesmo nome "
                f"({', '.join(sorted(repetidos))}) — não dá pra separar."
            )

        vistos |= campos


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

        if granularidade == "diaria" and personalizado.get("data_inicial"):
            return {
                "dia": {
                    "data_inicial": personalizado["data_inicial"],
                    "data_final": personalizado.get(
                        "data_final", personalizado["data_inicial"]
                    ),
                }
            }

        filtro = {}

        if personalizado.get("meses"):
            filtro["mes"] = personalizado["meses"]

        if personalizado.get("anos"):
            filtro["ano"] = personalizado["anos"]

        if not filtro:
            raise ConsultaInvalida(
                "periodo_personalizado precisa de 'meses'/'anos' (ou "
                "'data_inicial'/'data_final' em indicadores por data)."
            )

        return filtro

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

    if periodo == "mes_anterior":
        mes = hoje.month - 1 or 12
        ano = hoje.year if hoje.month > 1 else hoje.year - 1
        return {"dia": _intervalo_do_mes(ano, mes)}

    if periodo == "mesmo_mes_ano_anterior":
        return {"dia": _intervalo_do_mes(hoje.year - 1, hoje.month)}

    raise ConsultaInvalida(
        f"O período '{periodo}' não é suportado para indicadores diários."
    )


def _intervalo_do_mes(ano: int, mes: int) -> dict:
    ultimo_dia = calendar.monthrange(ano, mes)[1]

    return {
        "data_inicial": date(ano, mes, 1).isoformat(),
        "data_final": date(ano, mes, ultimo_dia).isoformat(),
    }


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


def _campos_de_contagem(dados: pd.DataFrame, campos: dict) -> set[str]:
    """
    Campos somados cuja coluna de origem é inteira (ex: quantidade de
    notas, respostas de NPS) — continuam inteiros no resultado, em vez
    de virar "534.0".
    """
    contagens = set()

    for nome_campo, especificacao in campos.items():
        coluna, agregacao, _ = _desempacotar_campo(especificacao)

        if agregacao == "sum" and pd.api.types.is_integer_dtype(dados[coluna]):
            contagens.add(nome_campo)

    return contagens


def _numero(valor, inteiro: bool):
    return int(round(float(valor))) if inteiro else round(float(valor), 2)


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
    inteiros = _campos_de_contagem(dados, campos)

    if not agrupar_por:
        item = {}

        for chave_dedup, campos_do_grupo in grupos_de_campos:
            dados_do_grupo = (
                dados.drop_duplicates(subset=list(chave_dedup))
                if chave_dedup else dados
            )

            for nome_campo, (coluna, agregacao) in campos_do_grupo.items():
                valor = getattr(dados_do_grupo[coluna], agregacao)()
                item[nome_campo] = _numero(valor, nome_campo in inteiros)

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
            item[nome_campo] = _numero(linha[nome_campo], nome_campo in inteiros)

        resultados.append(item)

    mapa_rca_nome_func = indicador_def.get("rca_nome_mapa")

    if "rca" in agrupar_por and mapa_rca_nome_func:
        mapa_rca_nome = mapa_rca_nome_func()

        for item in resultados:
            item["rca_nome"] = mapa_rca_nome.get(item["rca"])

    return resultados


def _filtros_efetivos(
    indicador_def: dict,
    consulta: dict,
    periodo: str | None,
    periodo_personalizado: dict | None,
) -> dict:
    """
    Os filtros que valem de verdade pra um período: os "filtros" da
    consulta mais o que o período resolve (ex: "mes_atual" vira
    mes/ano). Quem precisa saber "qual ano/mês foi consultado" (variação
    mês a mês, necessidade diária) tem que olhar AQUI, não só pros
    "filtros" — o período pode ter vindo por "periodo"/
    "periodo_personalizado".
    """
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
        filtros_do_periodo = resolver_periodo(
            periodo,
            periodo_personalizado,
            indicador_def["granularidade_periodo"],
        )

        # Um período nunca pode ser ignorado em silêncio: se ele gera
        # um filtro numa dimensão que o indicador não tem, é erro.
        for dimensao in filtros_do_periodo:
            if dimensao not in indicador_def["dimensoes"]:
                raise ConsultaInvalida(
                    f"O período '{periodo}' não é compatível com esse "
                    "indicador (ele não filtra por essa dimensão)."
                )

        filtros.update(filtros_do_periodo)

    return filtros


def _consultar_periodo(
    indicador_def: dict,
    consulta: dict,
    periodo: str | None,
    periodo_personalizado: dict | None,
    agrupar_por: list[str],
    rcas_validos: set[int] | None = None,
) -> tuple[list[dict], set[int] | None]:
    filtros = _filtros_efetivos(
        indicador_def, consulta, periodo, periodo_personalizado
    )

    dados, rcas_validos = buscar_dados_brutos(
        indicador_def, agrupar_por, filtros, rcas_validos
    )

    if dados.empty:
        return [], rcas_validos

    # As fórmulas derivadas (ex: NPS, % de atingimento) são calculadas
    # AQUI, em cada período, antes de qualquer comparação — assim
    # "comparar_com" e a variação mês a mês conseguem comparar
    # também os campos calculados, não só os somados.
    resultado = _aplicar_derivados(
        _aplicar_agrupamento(dados, indicador_def, agrupar_por), indicador_def
    )

    # Quem pergunta por código de filial precisa ver o código de cada
    # linha — sem ele a IA adivinha o código pelo nome e erra.
    if "filial" in agrupar_por:
        for linha in resultado:
            linha["codigo_filial"] = CODIGO_POR_NOME.get(linha["filial"])

    return resultado, rcas_validos


def _juntar_indicadores(
    resultado: list[dict],
    outro: list[dict],
    agrupar_por: list[str],
    campos_resultado: list[str],
    campos_outro: list[str],
) -> list[dict]:
    """
    Junta o resultado de dois indicadores pela chave do agrupamento
    (filial, mês, ano...). Quem existe só num dos lados fica com os
    campos do outro vazios (None) — os filtros e a ordenação já ignoram
    vazios, e a IA avisa que faltou dado.
    """
    def chave(linha):
        return tuple(linha[dimensao] for dimensao in agrupar_por)

    juntas = {
        chave(linha): {**dict.fromkeys(campos_outro), **linha}
        for linha in resultado
    }

    for linha in outro:
        base = juntas.setdefault(chave(linha), dict.fromkeys(campos_resultado))
        base.update(linha)

    return [juntas[chave_] for chave_ in sorted(juntas)]


def _consultar_indicadores(
    indicadores: list[str],
    consulta: dict,
    periodo: str | None,
    periodo_personalizado: dict | None,
    agrupar_por: list[str],
    rcas_validos: set[int] | None = None,
) -> tuple[list[dict], set[int] | None]:
    """
    Consulta o indicador principal e, se a consulta tiver "cruzar_com",
    cada indicador extra (mesmos filtros e período, cada um com as suas
    fórmulas), juntando tudo numa tabela só.
    """
    definicoes = [catalogo.INDICADORES[nome] for nome in indicadores]

    resultado, rcas_validos = _consultar_periodo(
        definicoes[0], consulta, periodo, periodo_personalizado,
        agrupar_por, rcas_validos,
    )
    campos_resultado = _campos_do_indicador(definicoes[0])

    for definicao in definicoes[1:]:
        outro, _ = _consultar_periodo(
            definicao, consulta, periodo, periodo_personalizado, agrupar_por
        )
        campos_outro = _campos_do_indicador(definicao)
        resultado = _juntar_indicadores(
            resultado, outro, agrupar_por, campos_resultado, campos_outro
        )
        campos_resultado = campos_resultado + campos_outro

    resultado = _aplicar_derivados(
        resultado, {"derivados": _derivados_do_cruzamento(indicadores)}
    )

    return resultado, rcas_validos


def _combinar_comparacao(
    atual: list[dict],
    anterior: list[dict],
    agrupar_por,
    campos,
    incluir_so_do_outro_lado: bool = False,
) -> list[dict]:
    """
    Junta o resultado atual com o de comparação (mesma chave de
    agrupamento), calculando diferença e percentual de cada campo
    numérico — mesma fórmula usada em toda variação "anterior" do
    projeto (variacao_utils.calcular_diferenca_percentual).

    Numa comparação de PERÍODOS, só interessa o que existe no período
    atual. Numa comparação entre ITENS (`incluir_so_do_outro_lado`), um
    mês em que só o outro lado tem dado também entra (com o lado vazio
    como None) e o resultado sai ordenado pela chave.
    """
    def chave(item):
        return tuple(item[dimensao] for dimensao in agrupar_por)

    mapa_anterior = {chave(item): item for item in anterior}
    resultados = []

    def combinar(item_atual, item_anterior, base):
        combinado = dict(base)

        for campo in campos:
            diferenca, percentual = calcular_diferenca_percentual(
                item_anterior.get(campo), item_atual.get(campo)
            )
            combinado[f"{campo}_anterior"] = item_anterior.get(campo)
            combinado[f"diferenca_{campo}"] = diferenca
            combinado[f"percentual_{campo}"] = percentual

        return combinado

    for item in atual:
        resultados.append(combinar(item, mapa_anterior.get(chave(item), {}), item))

    if incluir_so_do_outro_lado:
        vistas = {chave(item) for item in atual}

        for chave_outra, item_anterior in mapa_anterior.items():
            if chave_outra not in vistas:
                base = {
                    dimensao: item_anterior[dimensao] for dimensao in agrupar_por
                }
                resultados.append(
                    combinar({}, item_anterior, {**dict.fromkeys(campos), **base})
                )

        resultados.sort(key=chave)

    return resultados


def _aplicar_variacao_temporal(
    resultado: list[dict],
    agrupar_por: list[str],
    indicador_def: dict,
    filtros: dict,
) -> list[dict]:
    """
    Quando a consulta agrupa por "mes" e/ou "ano", preenche
    automaticamente a variação em relação ao período anterior — mesmo
    padrão já usado por NPS e Metas antes deste motor existir (veja
    variacao_utils.calcular_variacao_sequencial):
    - "ano" agrupado, com 2+ anos filtrados: compara cada ano com o
      ano anterior da lista — e, se "mes" também estiver agrupado, cada
      mês com o MESMO mês do ano anterior (campos
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

    if not campo or not resultado or not {"mes", "ano"} & set(agrupar_por):
        return resultado

    dimensoes_extras = [
        dimensao for dimensao in agrupar_por if dimensao not in ("mes", "ano")
    ]

    anos = filtros.get("ano")
    anos = anos if isinstance(anos, list) else None

    if "ano" in agrupar_por and anos and len(anos) >= 2:
        posicao_do_ano = {ano: indice for indice, ano in enumerate(anos)}

        def grupo(item):
            return (
                tuple(item[dimensao] for dimensao in dimensoes_extras),
                item["mes"] if "mes" in agrupar_por else None,
            )

        calcular_variacao_sequencial(
            resultado,
            campo_valor=campo,
            sufixo="ano_anterior",
            chave_grupo=grupo,
            chave_ordem=lambda item: (
                grupo(item), posicao_do_ano.get(item["ano"], len(anos)),
            ),
            incluir_valor_anterior_como=f"{campo}_ano_anterior",
        )
        return resultado

    if "mes" in agrupar_por and "ano" not in agrupar_por and anos and len(anos) == 1:
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
    - colunas (opcional): campos que a TABELA deve mostrar (só o que a
      pergunta pediu); o resultado completo segue indo pra IA.
    - comparar_filtros (opcional): compara DOIS ITENS da mesma dimensão
      (ex: filial A x filial B): a consulta é rodada de novo com esses
      filtros no lugar dos originais e o resultado ganha
      campo_anterior/diferenca_campo/percentual_campo (A menos B). A
      dimensão comparada não pode estar em agrupar_por.
    - cruzar_com (opcional): lista de outros indicadores, consultados
      com os mesmos filtros/período e juntados por filial/estado/mês/ano
      (ex: NPS cruzado com meta, pra "maior NPS que bateu a meta").
    - ordenar_por (opcional): {"campo": ..., "ordem": "desc"|"asc"
      (padrão "desc"), "limite": N} — ordena o resultado por um campo
      e corta pros N primeiros, de forma exata. Use pra "os N
      maiores/menores" em vez de confiar na IA pra comparar uma lista
      grande de itens "de olho".
    """
    consulta = _normalizar_comparacoes(consulta)
    validar_consulta(consulta)

    indicador = consulta["indicador"]
    indicador_def = catalogo.INDICADORES[indicador]
    agrupar_por = consulta.get("agrupar_por") or []
    cruzar_com = consulta.get("cruzar_com") or []
    indicadores = [indicador, *cruzar_com]

    resultado, rcas_validos = _consultar_indicadores(
        indicadores,
        consulta,
        consulta.get("periodo"),
        consulta.get("periodo_personalizado"),
        agrupar_por,
    )

    comparar_com = consulta.get("comparar_com")
    comparar_filtros = consulta.get("comparar_filtros")

    if comparar_com:
        # Reaproveita o MESMO conjunto de RCAs válidos calculado pro
        # período principal — ver docstring de buscar_dados_brutos.
        resultado_comparacao, _ = _consultar_indicadores(
            indicadores, consulta, comparar_com,
            consulta.get("comparar_com_personalizado"), agrupar_por,
            rcas_validos=rcas_validos,
        )
        campos_comparaveis = _campos_da_consulta(indicadores)
        resultado = _combinar_comparacao(
            resultado, resultado_comparacao, agrupar_por, campos_comparaveis,
        )
    elif comparar_filtros:
        # Comparação ENTRE ITENS (ex: filial A x filial B, mês a mês): a
        # mesma consulta rodada de novo com os filtros trocados. O lado A
        # vira o valor, o lado B o "_anterior".
        filtros_b = {**(consulta.get("filtros") or {}), **comparar_filtros}
        resultado_b, _ = _consultar_indicadores(
            indicadores, {**consulta, "filtros": filtros_b},
            consulta.get("periodo"), consulta.get("periodo_personalizado"),
            agrupar_por,
        )
        campos_comparaveis = _campos_da_consulta(indicadores)
        resultado = _combinar_comparacao(
            resultado, resultado_b, agrupar_por, campos_comparaveis,
            incluir_so_do_outro_lado=True,
        )
        lado_a = _nome_do_lado(
            indicador_def, consulta.get("filtros") or {}, list(comparar_filtros)
        )
        lado_b = _nome_do_lado(indicador_def, filtros_b, list(comparar_filtros))
    elif not cruzar_com:
        # (variação mês a mês e necessidade diária são do indicador
        # principal — numa consulta cruzada ficariam ambíguas)
        filtros_efetivos = _filtros_efetivos(
            indicador_def,
            consulta,
            consulta.get("periodo"),
            consulta.get("periodo_personalizado"),
        )
        resultado = _aplicar_variacao_temporal(
            resultado, agrupar_por, indicador_def, filtros_efetivos
        )
        resultado = _aplicar_necessidade_diaria(
            resultado, agrupar_por, indicador_def, filtros_efetivos
        )

    for filtro_calculado in consulta.get("filtros_calculados") or []:
        resultado = _aplicar_filtro_calculado(resultado, filtro_calculado)

    resultado = _aplicar_ordenacao(resultado, consulta.get("ordenar_por"))

    resposta = {
        "encontrado": bool(resultado),
        "indicador": indicador,
        "cruzado_com": cruzar_com or None,
        "filtros_aplicados": consulta.get("filtros"),
        "agrupar_por": agrupar_por or None,
        "resultados": resultado,
    }

    if comparar_filtros:
        resposta["comparacao_entre"] = {
            "a": lado_a,
            "b": lado_b,
            "como_ler": (
                f"Em cada campo, o valor do campo é de {lado_a}; "
                f"'{{campo}}_anterior' é de {lado_b}; "
                f"'diferenca_{{campo}}' = {lado_a} menos {lado_b}; "
                f"'percentual_{{campo}}' = essa diferença em % sobre {lado_b}."
            ),
        }

    # Comparação entre itens sempre tem tabela: sem "colunas", só o campo
    # principal (as colunas de comparação vêm junto).
    colunas = consulta.get("colunas") or (
        [indicador_def["campo_principal"]]
        if comparar_filtros and indicador_def.get("campo_principal") else None
    )

    if colunas:
        rotulos = None

        if comparar_filtros:
            rotulos = {}

            for coluna in colunas:
                rotulos[coluna] = lado_a
                rotulos[f"{coluna}_anterior"] = lado_b
                rotulos[f"diferenca_{coluna}"] = f"Diferença ({lado_a} − {lado_b})"
                rotulos[f"percentual_{coluna}"] = f"Diferença % ({lado_a} vs {lado_b})"

        resposta["tabela"] = _linhas_da_tabela(resultado, colunas, rotulos)

    return resposta
