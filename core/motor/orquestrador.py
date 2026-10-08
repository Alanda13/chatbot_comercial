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

from core.motor import catalogo
from core.motor import motor_metricas
from core.exceptions import ConsultaInvalida
from core.repositories.filiais_repository import CODIGO_POR_NOME
from core.motor.variacao_utils import (
    calcular_diferenca_percentual,
    calcular_variacao_sequencial,
)

_ORDEM_RESOLUCAO_DIMENSOES = ("filial", "rca", "supervisor")

# Resolvedores que recebem as filiais já resolvidas da consulta (pra
# desempatar nomes iguais em filiais diferentes) e devolvem uma LISTA de
# valores (ex: um nome de empresa vira todas as lojas dela).
_RESOLVEDORES_COM_FILIAL = (
    "rca", "supervisor", "cliente", "empresa", "produto", "familia", "grupo",
)

# Campos que descrevem o item agrupado (nome/CNPJ/cidade do cliente...)
# — identificação, não métrica: vão sempre pra tabela.
_CAMPOS_DE_ATRIBUTO = tuple(
    campo
    for atributos in catalogo.ATRIBUTOS_DIMENSAO.values()
    for campo in atributos
)

# Dimensões em que os indicadores usam o MESMO valor nas bases (o nome
# padrão da filial, o mês, o ano) — só por elas dá pra juntar dois
# indicadores. "rca" fica de fora: faturamento usa o código e a meta de
# tonelada usa o nome, então a junção sairia vazia sem avisar.
_DIMENSOES_DE_CRUZAMENTO = ("filial", "estado", "mes", "ano")

# As outras dimensões só cruzam quando TODOS os indicadores da consulta as
# identificam do mesmo jeito (mesma coluna e mesmo resolvedor) — ex:
# faturamento, meta e desconto usam o código (COD_RCA), então cruzam por
# RCA; a meta de tonelada usa o nome, então não cruza com eles por RCA.
# Faturamento e desconto têm produto/grupo/cliente; a meta não.


def _mesma_identificacao(indicadores: list[str], dimensao: str) -> bool:
    definicoes = [catalogo.INDICADORES[nome] for nome in indicadores]

    if any(dimensao not in definicao["dimensoes"] for definicao in definicoes):
        return False

    identificacoes = {
        (
            definicao["dimensoes"][dimensao],
            definicao.get("resolver_dimensao", {}).get(dimensao),
        )
        for definicao in definicoes
    }

    return len(identificacoes) == 1

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

        grupo = ordenar_por.get("por")

        if grupo is not None:
            if grupo not in (consulta.get("agrupar_por") or []):
                raise ConsultaInvalida(
                    f"'ordenar_por.por' ('{grupo}') precisa estar em 'agrupar_por'."
                )

            if (
                consulta.get("comparar_com") or consulta.get("comparar_filtros")
                or consulta.get("cruzar_com")
            ):
                raise ConsultaInvalida(
                    "'ordenar_por.por' não funciona junto com comparação "
                    "nem com cruzamento de indicadores."
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
    os derivados do cruzamento (sem repetir o campo que dois indicadores
    têm em comum)."""
    return list(dict.fromkeys([
        *(
            campo
            for nome in indicadores
            for campo in _campos_do_indicador(catalogo.INDICADORES[nome])
        ),
        *(derivado["nome"] for derivado in _derivados_do_cruzamento(indicadores)),
    ]))


def _linhas_da_tabela(
    resultado: list[dict],
    colunas: list[str],
    rotulos: dict | None = None,
    comparar: list[str] | None = None,
) -> list[dict]:
    """
    As linhas que vão pra tabela da tela: só a identificação (filial, mês,
    ...), os campos que a pergunta pediu ("colunas") e a comparação deles
    (anterior/diferença/variação). O resultado completo continua indo pra
    IA; só a TABELA é enxuta. "_colunas_pedidas" avisa a tela de que a
    escolha foi feita aqui (veja app.preparar_tabela); "_rotulos", quando
    há, troca o título de colunas (ex: os nomes das duas filiais).
    `comparar`: as colunas que ganham a comparação (padrão: todas).
    """
    comparacoes = {
        nome
        for coluna in (colunas if comparar is None else comparar)
        for nome in (
            f"{coluna}_anterior", f"diferenca_{coluna}", f"percentual_{coluna}"
        )
    }
    fixas = {*catalogo.DIMENSOES_VALIDAS, "rca_nome", *_CAMPOS_DE_ATRIBUTO}

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
        if dimensao in _DIMENSOES_DE_CRUZAMENTO:
            continue

        # Qualquer outra (rca, supervisor, cliente, produto, grupo...) cruza
        # quando TODOS os indicadores a identificam do mesmo jeito.
        if _mesma_identificacao(indicadores, dimensao):
            continue

        raise ConsultaInvalida(
            "Só é possível cruzar indicadores agrupando por "
            f"{', '.join(_DIMENSOES_DE_CRUZAMENTO)} — ou por outra dimensão "
            "quando todos os indicadores a identificam do mesmo jeito. A "
            f"dimensão '{dimensao}' não tem o mesmo valor em todas as bases "
            "desta consulta (ex: a meta não é separada por produto nem cliente)."
        )

    # Campo com o mesmo nome em dois indicadores só é aceito quando é o
    # MESMO dado (mesma base, mesma coluna, mesma soma) — ex: o
    # "valor_desconto" do faturamento e do desconto, os dois do
    # faturamento_mensal.csv: vira uma coluna só. Nome igual com dado
    # diferente (faturamento x faturamento_diario) não dá pra separar.
    vistos: dict[str, tuple] = {}

    for nome in indicadores:
        definicao = catalogo.INDICADORES[nome]
        identidades = {
            campo: (definicao.get("carregar"), definicao["campos"].get(campo))
            for campo in _campos_do_indicador(definicao)
        }
        repetidos = [
            campo for campo, identidade in identidades.items()
            if campo in vistos and (
                identidade[1] is None or vistos[campo] != identidade
            )
        ]

        if repetidos:
            raise ConsultaInvalida(
                "Os indicadores cruzados têm campos com o mesmo nome "
                f"({', '.join(sorted(repetidos))}) — não dá pra separar."
            )

        vistos.update(identidades)


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

        if periodo == "ano_anterior":
            return {"ano": [hoje.year - 1]}

        raise ConsultaInvalida(
            f"O período '{periodo}' não é suportado para indicadores "
            "mensais (eles não têm dado por dia/semana)."
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

    if periodo == "semana_anterior":
        inicio_semana = hoje - timedelta(days=hoje.weekday() + 7)
        return {
            "dia": {
                "data_inicial": inicio_semana.isoformat(),
                "data_final": (inicio_semana + timedelta(days=6)).isoformat(),
            }
        }

    if periodo == "ano_anterior":
        return {
            "dia": {
                "data_inicial": date(hoje.year - 1, 1, 1).isoformat(),
                "data_final": date(hoje.year - 1, 12, 31).isoformat(),
            }
        }

    raise ConsultaInvalida(
        f"O período '{periodo}' não é suportado para indicadores diários."
    )


_NOMES_MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
    "agosto", "setembro", "outubro", "novembro", "dezembro",
)


def _juntar_com_e(itens: list[str]) -> str:
    return itens[0] if len(itens) == 1 else f"{', '.join(itens[:-1])} e {itens[-1]}"


def _como_lista(valor) -> list:
    return valor if isinstance(valor, list) else [valor]


def _descrever_periodo(filtros: dict) -> dict | None:
    """
    O período que a consulta usou de fato (mês/ano/dias), com uma
    descrição pronta ("setembro de 2026", "de 01/09/2026 a 30/09/2026").
    Vai junto no resultado pra IA nunca precisar deduzir sozinha a que
    mês "mês passado" se refere — ela errava (ex: dizia "agosto" pra um
    dado de setembro).
    """
    periodo = {
        chave: filtros[chave] for chave in ("dia", "mes", "ano") if filtros.get(chave)
    }

    if not periodo:
        return None

    if "dia" in periodo:
        inicio = date.fromisoformat(str(periodo["dia"]["data_inicial"])[:10])
        fim = date.fromisoformat(
            str(periodo["dia"].get("data_final") or inicio)[:10]
        )
        descricao = (
            inicio.strftime("%d/%m/%Y") if inicio == fim
            else f"de {inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}"
        )
    else:
        meses = [_NOMES_MESES[int(mes) - 1] for mes in _como_lista(periodo.get("mes", []))]
        anos = [str(int(ano)) for ano in _como_lista(periodo.get("ano", []))]

        numeros = sorted(int(mes) for mes in _como_lista(periodo.get("mes", [])))

        # Meses seguidos viram intervalo: "de janeiro a setembro de 2026".
        if len(numeros) > 2 and numeros == list(range(numeros[0], numeros[-1] + 1)):
            meses = [
                f"de {_NOMES_MESES[numeros[0] - 1]} a {_NOMES_MESES[numeros[-1] - 1]}"
            ]

        if meses and anos:
            descricao = f"{_juntar_com_e(meses)} de {_juntar_com_e(anos)}"
        elif anos:
            descricao = _juntar_com_e(anos)
        else:
            descricao = f"{_juntar_com_e(meses)} (todos os anos)"

    return {**periodo, "descricao": descricao}


def _mes_atual_na_lista(resposta: dict) -> str | None:
    """
    "outubro de 2026" quando uma lista mês a mês inclui o mês atual (ex:
    desconto do Telha mês a mês: outubro, com 7 dias, "caía" 74%).
    """
    if "mes" not in (resposta.get("agrupar_por") or []):
        return None

    hoje = date.today()
    anos_filtro = [int(ano) for ano in _como_lista((resposta.get("filtros_aplicados") or {}).get("ano", []))]

    for linha in resposta["resultados"]:
        ano = linha.get("ano")
        do_ano_atual = int(ano) == hoje.year if ano is not None else anos_filtro == [hoje.year]

        if do_ano_atual and str(linha.get("mes")) == str(hoje.month):
            return f"{_NOMES_MESES[hoje.month - 1]} de {hoje.year}"

    return None


def _separar_mes_em_andamento(consulta: dict, indicadores: list[str]) -> dict | None:
    """
    "Atingimento de 2026" no começo de outubro somava a meta de outubro
    INTEIRA contra 5 dias de venda (Timon: 97,0% até setembro virava
    86,1%; Parnaíba, que bateu a meta, aparecia com 91%). Pros indicadores
    com meta ("acumulado_so_meses_fechados"), o acumulado do ano corrente
    usa só os meses fechados; quem chama consulta o mês em andamento à
    parte e devolve junto (resposta["mes_em_andamento"]).

    Só vale pro ano corrente sozinho, sem mês/dia pedidos, sem agrupar
    por mês (aí cada mês já aparece separado) e sem comparação. Devolve
    os filtros só com os meses fechados, ou None se a regra não se aplica.
    """
    if not any(
        catalogo.INDICADORES[nome].get("acumulado_so_meses_fechados")
        for nome in indicadores
    ):
        return None

    if (
        "mes" in (consulta.get("agrupar_por") or [])
        or consulta.get("comparar_com") or consulta.get("comparar_filtros")
    ):
        return None

    indicador_def = catalogo.INDICADORES[indicadores[0]]
    filtros = _filtros_efetivos(
        indicador_def, consulta, consulta.get("periodo"),
        consulta.get("periodo_personalizado"),
    )
    hoje = date.today()

    if (
        "mes" in filtros or "dia" in filtros
        or _como_lista(filtros.get("ano", [])) != [hoje.year]
        or hoje.month == 1
    ):
        return None

    return {**filtros, "mes": list(range(1, hoje.month))}


def _mesmos_meses_na_comparacao(consulta: dict, indicador_def: dict) -> dict | None:
    """
    Comparar o ano atual (incompleto) com outro ano comparava 9 meses com 12:
    "as filiais que mais cresceram de 2025 para 2026" (em 06/10/2026) dava
    quase todas caindo (Timon -27%, Tibiri -40%). Quando a consulta compara
    o ano atual inteiro com outro ano — "comparar_com" ou agrupando por 2+
    anos —, todos os anos usam os mesmos meses fechados (jan até o mês
    anterior). Devolve os filtros com esses meses, ou None.
    """
    if indicador_def["granularidade_periodo"] != "mensal":
        return None

    filtros = _filtros_efetivos(
        indicador_def, consulta, consulta.get("periodo"),
        consulta.get("periodo_personalizado"),
    )
    anos = _como_lista(filtros.get("ano", []))
    hoje = date.today()

    if (
        hoje.year not in anos or "mes" in filtros or "dia" in filtros
        or hoje.month == 1
    ):
        return None

    compara_anos = consulta.get("comparar_com") or (
        "ano" in (consulta.get("agrupar_por") or []) and len(anos) >= 2
    )

    if not compara_anos:
        return None

    return {**filtros, "mes": list(range(1, hoje.month))}


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
                if dimensao in _RESOLVEDORES_COM_FILIAL:
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
) -> set[tuple[str, int]]:
    """
    "RCA de uma filial" é, no negócio, quem tem meta cadastrada NAQUELA
    filial — não qualquer código que apareceu na base (contas genéricas/
    contábeis também vendem, mas não são vendedores de verdade). A
    validade é por (filial, código), nunca só pelo código sozinho: o
    mesmo código pode ser reaproveitado como conta genérica em várias
    filiais, com meta de verdade só em uma delas (ex: código 1,
    "COMERCIAL FERRONORTE LTDA-F01-MATRIZ", tem meta em Campos Sales mas
    aparece com meta zero em Timon, Areinha e outras) — somar a meta do
    código em todas as filiais da consulta juntas fazia esse código
    "vazar" como RCA válido pras filiais onde ele não tem meta nenhuma.
    Essa definição usa sempre a base de metas como referência, mesmo
    quando o indicador consultado é outro (faturamento) — é uma regra
    compartilhada entre indicadores, não específica de um.

    Contas da empresa ("COMERCIAL FERRONORTE LTDA-F09-TIMON",
    "FERROLESTE F08"...) têm meta (parte da meta da filial, somada pela
    rotina 8139), mas não são vendedores: ficam fora das listas de RCA.
    Pedidas pelo nome/código, continuam respondendo (esse filtro só vale
    quando a consulta agrupa por RCA sem RCA específico).
    """
    dados_meta = catalogo.INDICADORES["meta"]["carregar"]()

    if "CONTA_EMPRESA" in dados_meta.columns:
        dados_meta = dados_meta[~dados_meta["CONTA_EMPRESA"].astype(bool)]

    if filiais:
        dados_meta = dados_meta[dados_meta["FILIAL"].isin(filiais)]

    if anos:
        dados_meta = dados_meta[dados_meta["ANO"].isin(anos)]

    metas_por_rca = dados_meta.groupby(["FILIAL", "COD_RCA"])["VALOR_META"].sum()
    validos = metas_por_rca[metas_por_rca > 0].index

    return {(filial, int(codigo)) for filial, codigo in validos}


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
    Cada item de `rcas_validos` é um par (filial, código) — ver
    _rcas_com_meta_cadastrada.
    """
    carregar = indicador_def.get("carregar")

    fontes = {
        fonte
        for dimensao, fonte in indicador_def.get("fontes_por_dimensao", {}).items()
        if dimensao in agrupar_por or dimensao in filtros
    }

    # Cliente e produto vêm de arquivos diferentes (nenhum tem os dois).
    if len(fontes) > 1:
        raise ConsultaInvalida(
            "Ainda não dá pra combinar cliente com produto (ou forma de "
            "pagamento) na mesma consulta — consulte um de cada vez."
        )

    if fontes:
        carregar = fontes.pop()

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
        coluna_filial = indicador_def["dimensoes"]["filial"]
        chaves = pd.MultiIndex.from_arrays(
            [dados[coluna_filial], dados[coluna_rca]]
        )
        dados = dados[chaves.isin(rcas_validos)]

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
    # Campo cuja coluna o arquivo não tem fica de fora (ex: o faturamento
    # por produto não tem peso nem nº de notas) — em vez de dar erro.
    campos = {
        nome: especificacao
        for nome, especificacao in indicador_def["campos"].items()
        if _desempacotar_campo(especificacao)[0] in dados.columns
    }
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

            if dimensao in ("mes", "ano", "rca", "supervisor", "cliente", "produto"):
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

    for dimensao, coluna in zip(agrupar_por, colunas_agrupamento):
        atributos = {
            campo: definicao
            for campo, definicao in catalogo.ATRIBUTOS_DIMENSAO.get(dimensao, {}).items()
            if definicao[0] in dados.columns
        }

        if not atributos:
            continue

        colunas_atributo = [coluna_df for coluna_df, _ in atributos.values()]
        primeiro = dados.groupby(coluna)[colunas_atributo].first()

        for item in resultados:
            chave = item[dimensao]
            linha = primeiro.loc[chave] if chave in primeiro.index else None

            for campo, (coluna_df, _) in atributos.items():
                valor = None if linha is None else linha[coluna_df]
                item[campo] = None if pd.isna(valor) else str(valor)

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


def _itens_filtrados(
    dados: pd.DataFrame, indicador_def: dict, filtros: dict
) -> dict:
    """
    Pra cada filtro numa dimensão com atributos (cliente, empresa), os
    itens que sobraram com o nome/CNPJ — até 10 por dimensão.
    """
    itens = {}

    for dimensao in filtros:
        atributos = {
            campo: definicao
            for campo, definicao in catalogo.ATRIBUTOS_DIMENSAO.get(dimensao, {}).items()
            if definicao[0] in dados.columns
        }
        coluna = indicador_def["dimensoes"].get(dimensao)

        if not atributos or coluna is None:
            continue

        colunas_atributo = {campo: col for campo, (col, _) in atributos.items()}
        primeiro = dados.groupby(coluna)[list(colunas_atributo.values())].first()
        itens[dimensao] = [
            {
                dimensao: chave.item() if hasattr(chave, "item") else chave,
                **{
                    campo: None if pd.isna(linha[col]) else str(linha[col])
                    for campo, col in colunas_atributo.items()
                },
            }
            for chave, linha in primeiro.head(10).iterrows()
        ]

    return itens


def _consultar_periodo(
    indicador_def: dict,
    consulta: dict,
    periodo: str | None,
    periodo_personalizado: dict | None,
    agrupar_por: list[str],
    rcas_validos: set[int] | None = None,
    extras: dict | None = None,
) -> tuple[list[dict], set[int] | None]:
    """
    `extras`, quando informado, é preenchido com:
    - "itens_filtrados": nome/CNPJ dos itens filtrados (ex: a empresa
      de um filtro "empresa") — pra resposta citar o nome oficial;
    - "total" (só se `extras["calcular_total"]`): o total de TODAS as
      linhas agrupadas (mesmos dados, sem agrupamento) — pra IA nunca
      precisar somar a lista de cabeça (ex: o desconto da empresa
      inteira junto com a tabela por loja);
    - "totais_por_grupo" (só se `extras["total_por"]`): os mesmos dados
      agrupados só por essa dimensão (ex: o total de cada RCA, pra
      escolher os N RCAs com mais desconto — ver
      _aplicar_ordenacao_por_grupo).
    """
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

    if extras is not None:
        extras["itens_filtrados"] = _itens_filtrados(dados, indicador_def, filtros)

        if agrupar_por and extras.get("calcular_total"):
            extras["total"] = _aplicar_derivados(
                _aplicar_agrupamento(dados, indicador_def, []), indicador_def
            )[0]

        if extras.get("total_por"):
            extras["totais_por_grupo"] = _aplicar_derivados(
                _aplicar_agrupamento(dados, indicador_def, [extras["total_por"]]),
                indicador_def,
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
    extras: dict | None = None,
) -> tuple[list[dict], set[int] | None]:
    """
    Consulta o indicador principal e, se a consulta tiver "cruzar_com",
    cada indicador extra (mesmos filtros e período, cada um com as suas
    fórmulas), juntando tudo numa tabela só.
    """
    definicoes = [catalogo.INDICADORES[nome] for nome in indicadores]

    resultado, rcas_validos = _consultar_periodo(
        definicoes[0], consulta, periodo, periodo_personalizado,
        agrupar_por, rcas_validos, extras,
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

    Usa o campo definido em indicador_def["campo_variacao"] ou, sem ele,
    em "campo_principal" — o indicador que faz sentido acompanhar ao
    longo do tempo (ex: faturamento realizado, não a meta em si).
    Indicadores sem esses campos não recebem essa variação automática.
    """
    campo = indicador_def.get("campo_variacao") or indicador_def.get("campo_principal")

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

            # Faltando um campo (ex: peso no faturamento por produto), o
            # calculado fica vazio em vez de dar erro.
            item[derivado["nome"]] = (
                None if any(argumento is None for argumento in argumentos)
                else funcao(*argumentos)
            )

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


def _aplicar_ordenacao_por_grupo(
    resultado: list[dict], ordenar_por: dict, grupos: list
) -> list[dict]:
    """
    "Os N maiores e, dentro de cada um, os principais" (ex: os 5 RCAs que
    mais deram desconto e os 3 clientes de cada): `grupos` já vem na
    ordem do total de cada grupo (ver executar_consulta); aqui as linhas
    de cada grupo são ordenadas e cortadas em "limite" — nunca os N
    maiores PARES (RCA, cliente), que deixavam de fora um RCA com
    desconto alto espalhado em muitos clientes.

    Sem "limite" (ex: "o histórico mês a mês dos 3 maiores RCAs"), as
    linhas de cada grupo ficam na ordem natural (janeiro → dezembro) —
    reordenar pelo valor embaralhava os meses.
    """
    grupo = ordenar_por["por"]
    limite = ordenar_por.get("limite")
    por_ordem_e_limite = {
        "campo": ordenar_por["campo"],
        "ordem": ordenar_por.get("ordem", "desc"),
        "limite": limite,
    }

    def linhas_do_grupo(valor):
        linhas = [item for item in resultado if item.get(grupo) == valor]
        return _aplicar_ordenacao(linhas, por_ordem_e_limite) if limite else linhas

    return [linha for valor in grupos for linha in linhas_do_grupo(valor)]


_CAMPOS_DE_NOME = (
    "rca_nome", "supervisor_nome", "empresa_nome", "cliente_nome", "filial",
    "estado", "rca", "supervisor", "empresa", "cliente",
)


def _separar_sem_valor(
    resultado: list[dict], indicador_def: dict, ordenar_por: dict | None
) -> tuple[list[dict], dict | None]:
    """
    "Quem MENOS deu desconto" (ordem "asc") listava quem não deu desconto
    nenhum — ou só centavos de arredondamento (meio centavo por item
    vendido em kg/metro: 21,9 kg x R$ 10,35 = R$ 226,665 vira R$ 226,67 na
    tabela e R$ 226,66 na nota). Pros indicadores com
    "menor_ignora_abaixo_de" (campo, limite), quem fica abaixo do limite
    sai da lista e volta à parte (quantos e quais). Só muda a LISTA: os
    totais continuam somando tudo, iguais ao WinThor.
    """
    regra = indicador_def.get("menor_ignora_abaixo_de")

    if not regra or not ordenar_por or ordenar_por.get("ordem") != "asc" or ordenar_por.get("por"):
        return resultado, None

    campo, limite = regra
    sem_valor = [linha for linha in resultado if (linha.get(campo) or 0) < limite]

    if not sem_valor:
        return resultado, None

    def nome(linha):
        return next((str(linha[c]) for c in _CAMPOS_DE_NOME if linha.get(c) is not None), "")

    return (
        [linha for linha in resultado if (linha.get(campo) or 0) >= limite],
        {
            "quantidade": len(sem_valor),
            "itens": [nome(linha) for linha in sem_valor[:20]],
            "explicacao": (
                f"{campo} abaixo de R$ {limite:.2f} — nenhum desconto ou só "
                "centavos de arredondamento; ficaram fora da lista de 'menor'."
            ),
        },
    )


def _colunas_usadas_na_pergunta(consulta: dict, indicador_def: dict) -> list[str] | None:
    """
    Sem "colunas" da IA, numa consulta com ordenação ou filtro sobre a
    métrica (ou num cruzamento), a tabela mostra só o que a pergunta usou:
    o campo da ordem, os dos filtros e o que resume cada indicador cruzado. Antes a tela escolhia pelas
    palavras do texto da resposta — "RCAs com mais desconto que não bateram
    a meta" saía com 7 colunas (até "Faturamento de Tabela", puxado pela
    palavra "tabela" em "a lista completa está na tabela").
    """
    campos = [
        (consulta.get("ordenar_por") or {}).get("campo"),
        *(filtro.get("campo") for filtro in consulta.get("filtros_calculados") or []),
    ]

    # Num cruzamento, também o campo que resume CADA indicador (ex: "NPS e
    # atingimento por filial" ordenado pelo NPS saía só com a coluna NPS).
    if consulta.get("cruzar_com"):
        campos += [
            catalogo.INDICADORES[nome].get("campo_principal")
            for nome in [consulta["indicador"], *consulta["cruzar_com"]]
        ]

    if not any(campos):
        return None

    return list(dict.fromkeys(campo for campo in campos if campo))


def _periodo_curto(filtros: dict) -> str:
    """Período pra título de coluna: "2025", "set/2026", "jan-set/2026"."""
    anos = "/".join(str(int(ano)) for ano in _como_lista(filtros.get("ano", [])))
    meses = sorted(int(mes) for mes in _como_lista(filtros.get("mes", [])))

    if "dia" in filtros:
        inicio = date.fromisoformat(str(filtros["dia"]["data_inicial"])[:10])
        fim = date.fromisoformat(str(filtros["dia"].get("data_final") or inicio)[:10])
        return f"{inicio:%d/%m}–{fim:%d/%m/%Y}" if inicio != fim else f"{inicio:%d/%m/%Y}"

    if not meses:
        return anos

    nomes = [_NOMES_MESES[mes - 1][:3] for mes in meses]
    seguidos = meses == list(range(meses[0], meses[-1] + 1))

    if len(meses) == 1:
        return f"{nomes[0]}/{anos}"

    return f"{nomes[0]}-{nomes[-1]}/{anos}" if seguidos else f"{', '.join(nomes)}/{anos}"


def _rotulo_do_campo(campo: str, indicadores: list[str]) -> str:
    for nome in indicadores:
        exibicao = catalogo.INDICADORES[nome].get("exibicao", {}).get(campo)
        if exibicao:
            return exibicao["rotulo"]
    return campo.replace("_", " ").capitalize()


def _tipo_do_campo(campo: str, indicadores: list[str]) -> str | None:
    for nome in indicadores:
        exibicao = catalogo.INDICADORES[nome].get("exibicao", {}).get(campo)
        if exibicao:
            return exibicao.get("tipo")
    return None


def _colunas_da_comparacao_de_periodos(
    colunas: list[str], indicadores: list[str], atual: str, anterior: str
) -> tuple[list[str], dict]:
    """
    Tabela de comparação entre períodos que qualquer um entende: o campo do
    foco da pergunta nos DOIS períodos, com o período no título, e o quanto
    cresceu/caiu; os outros campos com o período atual entre parênteses.
    Antes: "Faturamento (anterior)", "Diferença Faturamento" — não dava pra
    saber de que período era cada coluna.
    """
    conhecidos = set(_campos_da_consulta(indicadores))
    foco = colunas[0]
    base = foco

    for prefixo in ("diferenca_", "percentual_"):
        if foco not in conhecidos and foco.startswith(prefixo):
            base = foco[len(prefixo):]

    variacao = foco if foco != base else f"percentual_{base}"
    novas = list(dict.fromkeys([f"{base}_anterior", base, variacao, *colunas[1:]]))
    rotulo = _rotulo_do_campo(base, indicadores)

    rotulos = {
        f"{base}_anterior": f"{rotulo} {anterior}",
        base: f"{rotulo} {atual}",
        f"diferenca_{base}": (
            "Cresceu/caiu (R$)" if _tipo_do_campo(base, indicadores) == "moeda"
            else "Cresceu/caiu"
        ),
        f"percentual_{base}": "Cresceu/caiu (%)",
    }

    for campo in colunas[1:]:
        if campo not in rotulos:
            rotulos[campo] = f"{_rotulo_do_campo(campo, indicadores)} ({atual})"

    return novas, rotulos


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
      e corta pros N primeiros, de forma exata. Com "por" (uma dimensão
      de agrupar_por) e "limite_grupos": M, escolhe os M grupos com
      maior total e corta em N linhas DENTRO de cada grupo (ex: os 5
      RCAs que mais deram desconto e os 3 clientes de cada). Use pra "os N
      maiores/menores" em vez de confiar na IA pra comparar uma lista
      grande de itens "de olho".
    """
    consulta = _normalizar_comparacoes(consulta)

    # Dimensão (rca, filial, mês...) em "colunas" é inofensiva — ela já
    # sai sempre na tabela quando é agrupada — então é descartada em vez
    # de derrubar a consulta inteira (a IA às vezes pede "rca" ali).
    if consulta.get("colunas"):
        consulta = {
            **consulta,
            "colunas": [
                coluna for coluna in consulta["colunas"]
                if coluna not in (
                    *catalogo.DIMENSOES_VALIDAS, "rca_nome", *_CAMPOS_DE_ATRIBUTO
                )
            ],
        }

    validar_consulta(consulta)

    indicador = consulta["indicador"]
    indicador_def = catalogo.INDICADORES[indicador]

    periodo_consultado = _descrever_periodo(
        _filtros_efetivos(
            indicador_def, consulta, consulta.get("periodo"),
            consulta.get("periodo_personalizado"),
        )
    )

    # Sem período, o resultado somaria todo o histórico (desde 2020) —
    # ex: "desconto do Mateus em Timon" dava R$ 205 mil, quase tudo de
    # 2020. Pros indicadores com "periodo_padrao", usa esse período (o ano
    # atual) e a resposta avisa. Vale pra TODOS os indicadores da consulta:
    # com o NPS (sem padrão) cruzado com o desconto, somava desde 2020.
    periodo_padrao = next(
        (
            catalogo.INDICADORES[nome]["periodo_padrao"]
            for nome in [indicador, *(consulta.get("cruzar_com") or [])]
            if catalogo.INDICADORES[nome].get("periodo_padrao")
        ),
        None,
    )
    periodo_assumido = periodo_consultado is None and periodo_padrao is not None

    if periodo_assumido:
        consulta = {**consulta, "periodo": periodo_padrao, "periodo_personalizado": None}
        periodo_consultado = _descrever_periodo(
            _filtros_efetivos(indicador_def, consulta, periodo_padrao, None)
        )

    agrupar_por = consulta.get("agrupar_por") or []

    filtros_mesmos_meses = _mesmos_meses_na_comparacao(consulta, indicador_def)
    mesmos_meses = filtros_mesmos_meses is not None

    if mesmos_meses:
        consulta = {
            **consulta, "periodo": None, "periodo_personalizado": None,
            "filtros": filtros_mesmos_meses,
        }
        periodo_consultado = _descrever_periodo(filtros_mesmos_meses)

    filtros_meses_fechados = _separar_mes_em_andamento(
        consulta, [indicador, *(consulta.get("cruzar_com") or [])]
    )
    mes_em_andamento = None

    if filtros_meses_fechados is not None:
        hoje = date.today()
        # Sem ordenar/limite: o parcial mostra os MESMOS itens do resultado
        # principal (filtrado mais abaixo), não o "top N" do mês.
        consulta_do_mes = {
            **consulta, "periodo": None, "periodo_personalizado": None,
            "filtros": {**filtros_meses_fechados, "mes": [hoje.month]},
            "ordenar_por": None,
        }
        parcial = executar_consulta(consulta_do_mes)
        mes_em_andamento = {
            "descricao": (
                f"{parcial['periodo_consultado']['descricao']} — mês em "
                f"andamento, com vendas até {hoje.strftime('%d/%m/%Y')}"
            ),
            "resultados": parcial["resultados"],
        }
        consulta = {
            **consulta, "periodo": None, "periodo_personalizado": None,
            "filtros": filtros_meses_fechados,
        }
        periodo_consultado = _descrever_periodo(filtros_meses_fechados)

    # Agrupada por 2+ anos, a consulta já traz a variação de um ano pro
    # outro (_aplicar_variacao_temporal). Um "comparar_com" a mais
    # comparava cada ano com ELE MESMO (Timon 2024 x 2024 = +0,00%, e
    # 2025 "sem dados") — então é descartado.
    anos_consultados = _como_lista((periodo_consultado or {}).get("ano", []))

    if consulta.get("comparar_com") and "ano" in agrupar_por and len(anos_consultados) >= 2:
        consulta = {**consulta, "comparar_com": None, "comparar_com_personalizado": None}

    cruzar_com = consulta.get("cruzar_com") or []
    indicadores = [indicador, *cruzar_com]

    comparar_com = consulta.get("comparar_com")
    comparar_filtros = consulta.get("comparar_filtros")

    # Total de todas as linhas: só na consulta simples (um indicador,
    # sem comparação e sem filtro sobre a métrica, que deixariam o
    # total diferente da soma das linhas mostradas).
    extras = {
        "calcular_total": not (
            cruzar_com or comparar_com or comparar_filtros
            or consulta.get("filtros_calculados")
        ),
        "total_por": (consulta.get("ordenar_por") or {}).get("por"),
    }

    resultado, rcas_validos = _consultar_indicadores(
        indicadores,
        consulta,
        consulta.get("periodo"),
        consulta.get("periodo_personalizado"),
        agrupar_por,
        extras=extras,
    )

    if (
        cruzar_com and agrupar_por and not comparar_com and not comparar_filtros
        and not consulta.get("filtros_calculados")
        # Por RCA a lista é só de quem tem meta: o total sem agrupar
        # (com canal único e contas da empresa) não seria a soma dela.
        and "rca" not in agrupar_por
    ):
        # Total da consulta cruzada: a mesma consulta sem agrupar (uma linha
        # com o total de cada indicador). Sem ele a IA somava só as 60
        # linhas que recebe (ex: "famílias de Metalon": R$ 15,8 mi de R$ 89,5 mi).
        total, _ = _consultar_indicadores(
            indicadores, consulta, consulta.get("periodo"),
            consulta.get("periodo_personalizado"), [], rcas_validos=rcas_validos,
        )
        if total:
            extras["total"] = total[0]

    if comparar_com:
        # Reaproveita o MESMO conjunto de RCAs válidos calculado pro
        # período principal — ver docstring de buscar_dados_brutos.
        resultado_comparacao, _ = _consultar_indicadores(
            indicadores, consulta, comparar_com,
            consulta.get("comparar_com_personalizado"), agrupar_por,
            rcas_validos=rcas_validos,
        )
        campos_comparaveis = _campos_da_consulta(indicadores)
        # Período principal sem nenhuma venda (ex: 10/08/2025, um domingo,
        # contra 20/08/2025): mostra o outro lado com o principal vazio,
        # em vez de descartar a comparação inteira.
        resultado = _combinar_comparacao(
            resultado, resultado_comparacao, agrupar_por, campos_comparaveis,
            incluir_so_do_outro_lado=not resultado,
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

    resultado, sem_desconto = _separar_sem_valor(
        resultado, indicador_def, consulta.get("ordenar_por")
    )
    resultado_antes_do_limite = resultado
    ordenar_por = consulta.get("ordenar_por")
    totais_por_grupo = None

    if ordenar_por and ordenar_por.get("por"):
        # O ranking dos grupos usa o total de CADA GRUPO (os mesmos dados
        # agrupados só por ele), não a soma das linhas — assim um campo
        # calculado (ex: % de desconto) também ordena certo.
        grupo = ordenar_por["por"]
        totais_por_grupo = _aplicar_ordenacao(
            extras.get("totais_por_grupo", []),
            {
                "campo": ordenar_por["campo"],
                "ordem": ordenar_por.get("ordem", "desc"),
                "limite": ordenar_por.get("limite_grupos"),
            },
        )
        resultado = _aplicar_ordenacao_por_grupo(
            resultado, ordenar_por, [linha[grupo] for linha in totais_por_grupo]
        )
    else:
        resultado = _aplicar_ordenacao(resultado, ordenar_por)

    resposta = {
        "encontrado": bool(resultado),
        "indicador": indicador,
        "cruzado_com": cruzar_com or None,
        "filtros_aplicados": consulta.get("filtros"),
        "periodo_consultado": periodo_consultado or {
            "descricao": "todo o histórico disponível (sem filtro de período)"
        },
        "agrupar_por": agrupar_por or None,
        "resultados": resultado,
    }

    if totais_por_grupo is not None:
        resposta["totais_por_grupo"] = totais_por_grupo

    if sem_desconto is not None:
        resposta["sem_desconto"] = sem_desconto

    if mesmos_meses:
        resposta["mesmo_periodo_nos_anos"] = (
            "O ano atual ainda não terminou: a comparação usa os mesmos meses "
            "fechados nos anos comparados. Diga isso na resposta (ex: "
            "\"comparando janeiro a setembro de 2025 e de 2026\")."
        )

    if ordenar_por and ordenar_por.get("campo"):
        # Dito com todas as letras: a IA dizia "maior percentual" numa
        # lista ordenada pelo valor em R$.
        sentido = "do menor para o maior" if ordenar_por.get("ordem") == "asc" else "do maior para o menor"
        dentro = f" dentro de cada {ordenar_por['por']}" if ordenar_por.get("por") else ""
        tipo = _tipo_do_campo(ordenar_por["campo"], indicadores)
        medida = " (valor em R$)" if tipo == "moeda" else " (percentual)" if tipo == "percentual" else ""
        resposta["criterio_da_ordem"] = (
            f"Ordenado por {_rotulo_do_campo(ordenar_por['campo'], indicadores).lower()}"
            f"{medida}, {sentido}{dentro}. Mostre ESSE valor de cada item (o "
            "outro pode vir junto, entre parênteses) e use a palavra certa "
            "(\"maior valor de desconto\" ≠ \"maior percentual\"), sem "
            "escrever \"critério da ordem\"."
        )

    mes_atual = _mes_atual_na_lista(resposta)

    if mes_atual:
        resposta["mes_atual_incompleto"] = (
            f"{mes_atual} ainda está em andamento (dados até hoje, "
            f"{date.today():%d/%m}): diga isso na resposta e que a variação "
            "desse mês não é comparável com os meses fechados."
        )

    if periodo_assumido:
        resposta["periodo_assumido"] = (
            "A pergunta não disse o período: foi usado o ano atual. Diga isso "
            "na resposta e que dá pra consultar outro período."
        )

    if mes_em_andamento is not None:
        def chave(linha):
            return tuple(linha.get(dimensao) for dimensao in agrupar_por)

        mostradas = {chave(linha) for linha in resultado}
        resposta["mes_em_andamento"] = {
            **mes_em_andamento,
            "resultados": [
                linha for linha in mes_em_andamento["resultados"]
                if chave(linha) in mostradas
            ],
        }

    if extras.get("itens_filtrados"):
        resposta["itens_filtrados"] = extras["itens_filtrados"]

    if extras.get("total"):
        resposta["total_de_todas_as_linhas"] = {
            **extras["total"],
            "quantidade_de_linhas": len(resultado_antes_do_limite),
            # ex: 149 linhas = 37 lojas x 2 anos — a IA não deve dizer
            # "149 lojas".
            "quantidade_por_dimensao": {
                dimensao: len({linha.get(dimensao) for linha in resultado_antes_do_limite})
                for dimensao in agrupar_por
            },
        }

        # Lista de RCAs = só vendedores com meta (sem canal único e sem
        # contas da empresa): a soma dela NÃO é o total da filial/empresa
        # do WinThor (ex: 02/10/2026, R$ 60.004,71 na lista x R$ 63.066,11
        # no dia). Avisa pra IA não apresentar uma pela outra.
        if (
            "rca" in agrupar_por and "rca" not in (consulta.get("filtros") or {})
            and indicador_def.get("rca_requer_meta_cadastrada")
        ):
            resposta["total_de_todas_as_linhas"]["observacao"] = (
                "Soma só dos RCAs listados (vendedores com meta). NÃO é o "
                "total da filial/empresa: esse inclui também contas da "
                "empresa e canal único. Não apresente esta soma como total "
                "da filial ou da empresa."
            )

    if comparar_com:
        resposta["periodo_comparado"] = _descrever_periodo(
            _filtros_efetivos(
                indicador_def, consulta, comparar_com,
                consulta.get("comparar_com_personalizado"),
            )
        )

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
    # Colunas escolhidas pelo sistema: a comparação (anterior/diferença/
    # variação) só pro 1º campo, o foco da pergunta. Antes cada campo ganhava
    # 3 colunas ("crescimento x desconto" saía com 9, até "Variação % Desconto").
    comparar = None

    rotulos = None

    if not colunas:
        colunas = _colunas_usadas_na_pergunta(consulta, indicador_def)
        comparar = colunas[:1] if colunas else None

        if colunas and comparar_com:
            colunas, rotulos = _colunas_da_comparacao_de_periodos(
                colunas, indicadores,
                _periodo_curto(_filtros_efetivos(
                    indicador_def, consulta, consulta.get("periodo"),
                    consulta.get("periodo_personalizado"),
                )),
                _periodo_curto(_filtros_efetivos(
                    indicador_def, consulta, comparar_com,
                    consulta.get("comparar_com_personalizado"),
                )),
            )
            comparar = []

    if colunas:

        if comparar_filtros:
            rotulos = {}

            for coluna in colunas:
                rotulos[coluna] = lado_a
                rotulos[f"{coluna}_anterior"] = lado_b
                rotulos[f"diferenca_{coluna}"] = f"Diferença ({lado_a} − {lado_b})"
                rotulos[f"percentual_{coluna}"] = f"Diferença % ({lado_a} vs {lado_b})"

        resposta["tabela"] = _linhas_da_tabela(resultado, colunas, rotulos, comparar)

    return resposta
