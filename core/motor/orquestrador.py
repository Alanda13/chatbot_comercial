"""
Motor de dados genérico: busca, filtra, agrupa e aplica fórmulas sobre
qualquer indicador do catalogo.py — sem uma função nova por pergunta.

Fluxo de executar_consulta(): valida → ajusta o período → busca e agrupa
os dados (com cruzamento/comparação) → ordena → monta a resposta pra IA
(resultados + avisos + linhas da tabela da tela).

Indicador novo = uma entrada em catalogo.py, nada aqui.
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

# Filial primeiro: os resolvedores de RCA/supervisor/cliente usam as
# filiais já resolvidas pra desempatar nomes iguais em filiais diferentes.
_ORDEM_RESOLUCAO_DIMENSOES = ("filial", "rca", "supervisor")

# Resolvedores que recebem as filiais e devolvem uma LISTA de valores
# (ex: um nome de empresa vira todas as lojas dela).
_RESOLVEDORES_COM_FILIAL = (
    "rca", "supervisor", "cliente", "empresa", "produto", "familia", "grupo",
    "venda",
)

# Nome/CNPJ/cidade que descrevem o item agrupado — identificação, não
# métrica: vão sempre pra tabela.
_CAMPOS_DE_ATRIBUTO = tuple(
    campo
    for atributos in catalogo.ATRIBUTOS_DIMENSAO.values()
    for campo in atributos
)

# Dimensões com o MESMO valor em todas as bases (nome padrão da filial,
# mês, ano): sempre dá pra cruzar indicadores por elas. As outras só
# quando todos os indicadores as identificam igual (ver _mesma_identificacao)
# — ex: a meta de tonelada usa o NOME do RCA, as outras bases o código.
_DIMENSOES_DE_CRUZAMENTO = ("filial", "estado", "mes", "ano")

_OPERADORES = {
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
    "==": operator.eq,
    "!=": operator.ne,
}

_NOMES_MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
    "agosto", "setembro", "outubro", "novembro", "dezembro",
)

# Pra nomear um item da lista de "sem desconto" (o primeiro que existir).
_CAMPOS_DE_NOME = (
    "rca_nome", "supervisor_nome", "empresa_nome", "cliente_nome", "filial",
    "estado", "rca", "supervisor", "empresa", "cliente",
)


# --- pequenos utilitários ----------------------------------------------------

def _como_lista(valor) -> list:
    return valor if isinstance(valor, list) else [valor]


def _juntar_com_e(itens: list[str]) -> str:
    return itens[0] if len(itens) == 1 else f"{', '.join(itens[:-1])} e {itens[-1]}"


def _chave(linha: dict, agrupar_por: list[str]) -> tuple:
    """Identificação de uma linha pelo agrupamento (ex: ("TIMON", 9))."""
    return tuple(linha.get(dimensao) for dimensao in agrupar_por)


def _numero(valor, inteiro: bool):
    return int(round(float(valor))) if inteiro else round(float(valor), 2)


def _dias(inicio: date, fim: date) -> dict:
    """Filtro de período dos indicadores por dia."""
    return {"dia": {"data_inicial": inicio.isoformat(), "data_final": fim.isoformat()}}


def _mes_inteiro(ano: int, mes: int) -> dict:
    return _dias(date(ano, mes, 1), date(ano, mes, calendar.monthrange(ano, mes)[1]))


def _inicio_e_fim(dia: dict) -> tuple[date, date]:
    inicio = date.fromisoformat(str(dia["data_inicial"])[:10])
    return inicio, date.fromisoformat(str(dia.get("data_final") or inicio)[:10])


def _com_filtros(consulta: dict, filtros: dict) -> dict:
    """A consulta com estes filtros no lugar do período original."""
    return {**consulta, "periodo": None, "periodo_personalizado": None, "filtros": filtros}


def _do_periodo_comparado(consulta: dict) -> dict:
    """A consulta no período de "comparar_com"."""
    return {
        **consulta,
        "periodo": consulta.get("comparar_com"),
        "periodo_personalizado": consulta.get("comparar_com_personalizado"),
    }


# --- validação ---------------------------------------------------------------

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


def _checar_dimensoes(indicadores: list[str], dimensoes, mensagem: str) -> None:
    """Todo indicador da consulta precisa aceitar a dimensão — um filtro
    que um deles não tem seria ignorado em silêncio."""
    for nome in indicadores:
        for dimensao in dimensoes:
            if not catalogo.dimensao_permitida(nome, dimensao):
                raise ConsultaInvalida(mensagem.format(dimensao=dimensao, nome=nome))


def _validar_anos(consulta: dict) -> None:
    """
    "Ano" que não é ano (ex: a IA mandou {"ano": [2026, 10]} querendo
    outubro) era aceito e a resposta comparava períodos errados ("jan-set de
    2026 e 10"): melhor um erro claro do que um número errado.
    """
    anos = [
        *_como_lista((consulta.get("filtros") or {}).get("ano", [])),
        *_como_lista((consulta.get("periodo_personalizado") or {}).get("anos", [])),
        *_como_lista((consulta.get("comparar_com_personalizado") or {}).get("anos", [])),
    ]

    for ano in anos:
        try:
            valido = 2000 <= int(ano) <= date.today().year + 1
        except (TypeError, ValueError):
            valido = False

        if not valido:
            raise ConsultaInvalida(
                f"'{ano}' não é um ano. Mês vai em 'mes' (filtros) ou 'meses' "
                "(periodo_personalizado), não junto com o ano."
            )


def _sem_ordem_por_contagem(consulta: dict) -> dict:
    """
    Ordenar por uma contagem de X agrupando pelo próprio X (ex: "clientes
    novos" de cada cliente) não muda nada: cada um tem 0 ou 1. A ordem sai e
    a consulta segue.
    """
    ordenar_por = consulta.get("ordenar_por") or {}
    agrupar_por = consulta.get("agrupar_por") or []

    for nome in [consulta.get("indicador"), *(consulta.get("cruzar_com") or [])]:
        especificacao = (catalogo.INDICADORES.get(nome) or {}).get("campos", {}).get(ordenar_por.get("campo"))
        contado = especificacao and _desempacotar_campo(especificacao)[2].get("conta")

        if contado and contado in agrupar_por:
            return {**consulta, "ordenar_por": None}

    return consulta


def _campo_da_participacao(consulta: dict) -> str | None:
    """O campo pedido; sem campo, o principal se ele se soma — senão o 1º
    valor somado (desconto: o valor em R$, não o %)."""
    indicador_def = catalogo.INDICADORES[consulta["indicador"]]
    pedido = (consulta.get("participacao") or {}).get("campo")

    if pedido:
        return pedido

    somados = [
        nome for nome, especificacao in indicador_def["campos"].items()
        if _desempacotar_campo(especificacao)[1] == "sum"
    ]
    principal = indicador_def.get("campo_principal")
    return principal if principal in somados else next(iter(somados), principal)


def _validar_participacao(consulta: dict) -> None:
    """Participação = um campo SOMADO de cada item ÷ o total do recorte:
    % de desconto, NPS ou nº de clientes não se dividem assim."""
    pedido = consulta["participacao"]

    if not isinstance(pedido, dict):
        raise ConsultaInvalida("'participacao' deve ser um dicionário: {\"dentro_de\": [...]}.")

    if consulta.get("comparar_com") or consulta.get("comparar_filtros"):
        raise ConsultaInvalida(
            "A participação não combina com comparação na mesma consulta: "
            "consulte cada período (ou item) separado."
        )

    indicador_def = catalogo.INDICADORES[consulta["indicador"]]
    campo = _campo_da_participacao(consulta)
    especificacao = indicador_def["campos"].get(campo)

    if especificacao is None or _desempacotar_campo(especificacao)[1] != "sum":
        rotulo = indicador_def.get("exibicao", {}).get(campo, {}).get("rotulo", campo)
        raise ConsultaInvalida(
            f"Não dá pra calcular participação de '{rotulo}': só de valores que "
            "se somam (ex: faturamento, venda bruta, valor de desconto)."
        )

    for dimensao in pedido.get("dentro_de") or []:
        if dimensao not in indicador_def["dimensoes"]:
            raise ConsultaInvalida(f"A dimensão '{dimensao}' não existe em '{consulta['indicador']}'.")


def validar_consulta(consulta: dict) -> None:
    """Rejeita indicador, dimensão, período, coluna ou ordenação fora do
    catálogo, com uma mensagem clara (ConsultaInvalida)."""
    indicador = consulta.get("indicador")
    cruzar_com = consulta.get("cruzar_com") or []
    indicadores = [indicador, *cruzar_com]
    agrupar_por = consulta.get("agrupar_por") or []

    for nome in indicadores:
        if not catalogo.indicador_existe(nome):
            raise ConsultaInvalida(f"O indicador '{nome}' não existe no catálogo.")

    if consulta.get("participacao") is not None:
        _validar_participacao(consulta)

    if cruzar_com:
        _validar_cruzamento(indicadores, agrupar_por)

    _checar_dimensoes(
        indicadores, agrupar_por,
        "A dimensão '{dimensao}' não é permitida para o indicador '{nome}'.",
    )
    filtro_nao_permitido = "O filtro '{dimensao}' não é permitido para o indicador '{nome}'."
    _checar_dimensoes(indicadores, consulta.get("filtros") or {}, filtro_nao_permitido)

    for campo_periodo in ("periodo", "comparar_com"):
        valor_periodo = consulta.get(campo_periodo)

        if valor_periodo and valor_periodo not in catalogo.PERIODOS_VALIDOS:
            raise ConsultaInvalida(f"O período '{valor_periodo}' não é reconhecido.")

    _validar_anos(consulta)

    comparar_filtros = consulta.get("comparar_filtros")

    if comparar_filtros:
        if not isinstance(comparar_filtros, dict):
            raise ConsultaInvalida("'comparar_filtros' deve ser um dicionário.")

        for dimensao in comparar_filtros:
            if dimensao in agrupar_por:
                raise ConsultaInvalida(
                    f"A dimensão '{dimensao}' está em 'comparar_filtros' e "
                    "também em 'agrupar_por' — os dois lados não se casariam. "
                    "Tire-a do agrupamento."
                )

        _checar_dimensoes(indicadores, comparar_filtros, filtro_nao_permitido)

    invalidas = [
        coluna for coluna in consulta.get("colunas") or []
        if coluna not in _campos_da_consulta(indicadores)
        and coluna != "necessidade_diaria"
    ]

    if invalidas:
        raise ConsultaInvalida(
            f"A(s) coluna(s) {', '.join(map(str, invalidas))} não "
            "existe(m) para essa consulta."
        )

    ordenar_por = consulta.get("ordenar_por")

    if not ordenar_por:
        return

    campos_validos = set(_campos_da_consulta(indicadores))

    # "comparar_com" cria os campos de comparação na hora — também valem
    # pra ordenar (ex: pelo crescimento).
    if consulta.get("comparar_com"):
        for campo in list(campos_validos):
            campos_validos |= {
                f"{campo}_anterior", f"diferenca_{campo}", f"percentual_{campo}",
            }

    campo_ordenacao = ordenar_por.get("campo")

    if campo_ordenacao not in campos_validos:
        raise ConsultaInvalida(
            f"O campo '{campo_ordenacao}' não pode ser usado em "
            f"'ordenar_por' para o indicador '{indicador}'."
        )

    grupo = ordenar_por.get("por")

    if grupo is not None:
        if grupo not in agrupar_por:
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


def _validar_cruzamento(indicadores: list[str], agrupar_por: list[str]) -> None:
    if len(set(indicadores)) != len(indicadores):
        raise ConsultaInvalida("'cruzar_com' não pode repetir o indicador da consulta.")

    for dimensao in agrupar_por:
        if dimensao in _DIMENSOES_DE_CRUZAMENTO or _mesma_identificacao(indicadores, dimensao):
            continue

        raise ConsultaInvalida(
            "Só é possível cruzar indicadores agrupando por "
            f"{', '.join(_DIMENSOES_DE_CRUZAMENTO)} — ou por outra dimensão "
            "quando todos os indicadores a identificam do mesmo jeito. A "
            f"dimensão '{dimensao}' não tem o mesmo valor em todas as bases "
            "desta consulta (ex: a meta não é separada por produto nem cliente)."
        )

    # Campo com o mesmo nome em dois indicadores só é aceito quando é o
    # MESMO dado (mesma base e coluna — ex: "valor_desconto" do faturamento
    # e do desconto): vira uma coluna só. Dado diferente não dá pra separar.
    vistos: dict[str, tuple] = {}

    for nome in indicadores:
        definicao = catalogo.INDICADORES[nome]
        identidades = {
            campo: (definicao.get("carregar"), definicao["campos"].get(campo))
            for campo in _campos_do_indicador(definicao)
        }
        repetidos = [
            campo for campo, identidade in identidades.items()
            if campo in vistos and (identidade[1] is None or vistos[campo] != identidade)
        ]

        if repetidos:
            raise ConsultaInvalida(
                "Os indicadores cruzados têm campos com o mesmo nome "
                f"({', '.join(sorted(repetidos))}) — não dá pra separar."
            )

        vistos.update(identidades)


def _normalizar_comparacoes(consulta: dict) -> dict:
    """
    "comparar_com" (período x período) junto com "comparar_filtros" (item x
    item): cada item, período contra período (ex: "Timon e Lourival, 1º
    semestre de 2025 x 2024"). Vira uma consulta agrupada pela dimensão, com
    os dois itens nos filtros.
    """
    comparar_filtros = consulta.get("comparar_filtros")

    if not (comparar_filtros and consulta.get("comparar_com")):
        return consulta

    filtros = dict(consulta.get("filtros") or {})
    agrupar_por = list(consulta.get("agrupar_por") or [])

    for dimensao, valores in comparar_filtros.items():
        if dimensao in filtros:
            juntos = [*_como_lista(filtros[dimensao]), *_como_lista(valores)]
            filtros[dimensao] = list(dict.fromkeys(juntos))

        if dimensao not in agrupar_por:
            agrupar_por.append(dimensao)

    return {
        **consulta, "filtros": filtros, "agrupar_por": agrupar_por,
        "comparar_filtros": None,
    }


# --- campos ------------------------------------------------------------------

def _campos_do_indicador(indicador_def: dict) -> list[str]:
    """Campos somados + campos calculados (derivados) de um indicador."""
    return [
        *indicador_def["campos"],
        *(derivado["nome"] for derivado in indicador_def.get("derivados", [])),
    ]


def _sem_campos_fora_do_recorte(resultado: list[dict], consulta: dict) -> list[dict]:
    """
    Campo com a opção "so_com" (uma dimensão) só sai quando a consulta filtra,
    agrupa ou compara por ela — ex: "ativos só por outra filial" não tem
    sentido numa consulta da empresa toda nem numa só de RCA.
    """
    recorte = {
        *(consulta.get("filtros") or {}),
        *(consulta.get("agrupar_por") or []),
        *(consulta.get("comparar_filtros") or {}),
    }
    fora = [
        campo
        for nome in [consulta["indicador"], *(consulta.get("cruzar_com") or [])]
        for campo, especificacao in catalogo.INDICADORES[nome]["campos"].items()
        if (dimensao := _desempacotar_campo(especificacao)[2].get("so_com")) and dimensao not in recorte
    ]

    if not fora:
        return resultado

    def tirar(chave: str) -> bool:
        return any(
            chave in (campo, f"{campo}_anterior", f"diferenca_{campo}", f"percentual_{campo}")
            for campo in fora
        )

    return [{chave: valor for chave, valor in linha.items() if not tirar(chave)} for linha in resultado]


def _derivados_do_cruzamento(indicadores: list[str]) -> list[dict]:
    """Derivados que dependem de dois indicadores (catalogo.CRUZAMENTOS)
    cujos indicadores estão TODOS na consulta."""
    return [
        derivado
        for cruzamento in catalogo.CRUZAMENTOS
        if set(cruzamento["indicadores"]) <= set(indicadores)
        for derivado in cruzamento["derivados"]
    ]


def _campos_da_consulta(indicadores: list[str]) -> list[str]:
    """Todos os campos que a consulta produz, sem repetir o que dois
    indicadores têm em comum."""
    return list(dict.fromkeys([
        *(
            campo
            for nome in indicadores
            for campo in _campos_do_indicador(catalogo.INDICADORES[nome])
        ),
        *(derivado["nome"] for derivado in _derivados_do_cruzamento(indicadores)),
    ]))


def _exibicao_do_campo(campo: str, indicadores: list[str]) -> dict:
    """Rótulo e tipo do campo no catálogo (do primeiro indicador que o tem)."""
    return next(
        (
            catalogo.INDICADORES[nome]["exibicao"][campo]
            for nome in indicadores
            if campo in catalogo.INDICADORES[nome].get("exibicao", {})
        ),
        {},
    )


def _rotulo_do_campo(campo: str, indicadores: list[str]) -> str:
    return (
        _exibicao_do_campo(campo, indicadores).get("rotulo")
        or campo.replace("_", " ").capitalize()
    )


def _tipo_do_campo(campo: str, indicadores: list[str]) -> str | None:
    return _exibicao_do_campo(campo, indicadores).get("tipo")


# --- período -----------------------------------------------------------------

def resolver_periodo(periodo: str, personalizado: dict | None, granularidade: str) -> dict:
    """
    Traduz o vocabulário de período do catálogo (mes_atual, ano_atual,
    personalizado...) em filtros: meses/anos (indicadores mensais) ou um
    intervalo de datas (indicadores por dia).
    """
    hoje = date.today()

    if periodo == "personalizado":
        if not personalizado:
            raise ConsultaInvalida(
                "periodo_personalizado é obrigatório quando periodo='personalizado'."
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

    mes_anterior = hoje.month - 1 or 12
    ano_do_mes_anterior = hoje.year if hoje.month > 1 else hoje.year - 1

    if granularidade == "mensal":
        mensais = {
            "mes_atual": {"mes": [hoje.month], "ano": [hoje.year]},
            "ano_atual": {"ano": [hoje.year]},
            "mes_anterior": {"mes": [mes_anterior], "ano": [ano_do_mes_anterior]},
            "mesmo_mes_ano_anterior": {"mes": [hoje.month], "ano": [hoje.year - 1]},
            "ano_anterior": {"ano": [hoje.year - 1]},
        }

        if periodo in mensais:
            return mensais[periodo]

        raise ConsultaInvalida(
            f"O período '{periodo}' não é suportado para indicadores "
            "mensais (eles não têm dado por dia/semana)."
        )

    ontem = hoje - timedelta(days=1)
    inicio_da_semana = hoje - timedelta(days=hoje.weekday())
    inicio_da_semana_anterior = inicio_da_semana - timedelta(days=7)
    diarios = {
        "hoje": _dias(hoje, hoje),
        "ontem": _dias(ontem, ontem),
        "semana_atual": _dias(inicio_da_semana, hoje),
        "mes_atual": _dias(hoje.replace(day=1), hoje),
        "ano_atual": _dias(date(hoje.year, 1, 1), hoje),
        "mes_anterior": _mes_inteiro(ano_do_mes_anterior, mes_anterior),
        "mesmo_mes_ano_anterior": _mes_inteiro(hoje.year - 1, hoje.month),
        "semana_anterior": _dias(
            inicio_da_semana_anterior, inicio_da_semana_anterior + timedelta(days=6)
        ),
        "ano_anterior": _dias(date(hoje.year - 1, 1, 1), date(hoje.year - 1, 12, 31)),
    }

    if periodo in diarios:
        return diarios[periodo]

    raise ConsultaInvalida(
        f"O período '{periodo}' não é suportado para indicadores diários."
    )


_PERIODOS_EM_DIAS = ("hoje", "ontem", "semana_atual", "semana_anterior")


def _granularidade(indicador_def: dict, consulta: dict) -> str:
    """A do indicador; num mensal que também aceita dias ("aceita_dias",
    ex: clientes), "diaria" quando o período pedido é em dias."""
    periodo = consulta.get("periodo")
    em_dias = periodo in _PERIODOS_EM_DIAS or (
        periodo == "personalizado" and (consulta.get("periodo_personalizado") or {}).get("data_inicial")
    )
    return "diaria" if indicador_def.get("aceita_dias") and em_dias else indicador_def["granularidade_periodo"]


def _filtros_efetivos(indicador_def: dict, consulta: dict) -> dict:
    """
    Os filtros que valem de verdade: os "filtros" da consulta mais o que o
    "periodo" resolve (ex: "mes_atual" vira mês/ano). Quem precisa saber
    o ano/mês consultado olha AQUI — o período pode não estar nos filtros.
    """
    filtros = dict(consulta.get("filtros") or {})
    periodo = consulta.get("periodo")

    if periodo == "ano_anterior_ao_filtro":
        # Só como "comparar_com": o ano anterior a cada ano já filtrado.
        anos_atuais = filtros.get("ano")

        if not anos_atuais:
            raise ConsultaInvalida(
                "'ano_anterior_ao_filtro' exige que 'filtros' já tenha 'ano' definido."
            )

        return {**filtros, "ano": [ano - 1 for ano in anos_atuais]}

    if periodo:
        filtros_do_periodo = resolver_periodo(
            periodo, consulta.get("periodo_personalizado"), _granularidade(indicador_def, consulta),
        )

        # Um período nunca é ignorado em silêncio.
        for dimensao in filtros_do_periodo:
            if dimensao not in indicador_def["dimensoes"]:
                raise ConsultaInvalida(
                    f"O período '{periodo}' não é compatível com esse "
                    "indicador (ele não filtra por essa dimensão)."
                )

        filtros.update(filtros_do_periodo)

    return filtros


def _descrever_periodo(filtros: dict) -> dict | None:
    """
    O período usado de fato, com a descrição pronta ("setembro de 2026",
    "de 01/09/2026 a 30/09/2026"), pra IA não deduzir a que mês "mês
    passado" se refere.
    """
    periodo = {
        chave: filtros[chave] for chave in ("dia", "mes", "ano") if filtros.get(chave)
    }

    if not periodo:
        return None

    if "dia" in periodo:
        inicio, fim = _inicio_e_fim(periodo["dia"])
        descricao = (
            inicio.strftime("%d/%m/%Y") if inicio == fim
            else f"de {inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}"
        )
        return {**periodo, "descricao": descricao}

    numeros = sorted(int(mes) for mes in _como_lista(periodo.get("mes", [])))
    meses = [_NOMES_MESES[int(mes) - 1] for mes in _como_lista(periodo.get("mes", []))]
    anos = [str(int(ano)) for ano in _como_lista(periodo.get("ano", []))]

    # Meses seguidos viram intervalo: "de janeiro a setembro de 2026".
    if len(numeros) > 2 and numeros == list(range(numeros[0], numeros[-1] + 1)):
        meses = [f"de {_NOMES_MESES[numeros[0] - 1]} a {_NOMES_MESES[numeros[-1] - 1]}"]

    if meses and anos:
        descricao = f"{_juntar_com_e(meses)} de {_juntar_com_e(anos)}"
    elif anos:
        descricao = _juntar_com_e(anos)
    else:
        descricao = f"{_juntar_com_e(meses)} (todos os anos)"

    return {**periodo, "descricao": descricao}


def _periodo_curto(filtros: dict) -> str:
    """Período pra título de coluna: "2025", "set/2026", "jan-set/2026"."""
    anos = "/".join(str(int(ano)) for ano in _como_lista(filtros.get("ano", [])))
    meses = sorted(int(mes) for mes in _como_lista(filtros.get("mes", [])))

    if "dia" in filtros:
        inicio, fim = _inicio_e_fim(filtros["dia"])
        return f"{inicio:%d/%m}–{fim:%d/%m/%Y}" if inicio != fim else f"{inicio:%d/%m/%Y}"

    if not meses:
        return anos

    nomes = [_NOMES_MESES[mes - 1][:3] for mes in meses]
    seguidos = meses == list(range(meses[0], meses[-1] + 1))

    if len(meses) == 1:
        return f"{nomes[0]}/{anos}"

    return f"{nomes[0]}-{nomes[-1]}/{anos}" if seguidos else f"{', '.join(nomes)}/{anos}"


def _com_meses_fechados(consulta: dict, indicador_def: dict, anos_aceitos) -> dict | None:
    """
    Os filtros da consulta com o ano atual só até o mês passado — ou None
    se não se aplica (já tem mês/dia, é janeiro, ou `anos_aceitos(anos,
    ano_atual)` diz que não).
    """
    filtros = _filtros_efetivos(indicador_def, consulta)
    anos = _como_lista(filtros.get("ano", []))
    hoje = date.today()

    if "mes" in filtros or "dia" in filtros or hoje.month == 1:
        return None

    if not anos_aceitos(anos, hoje.year):
        return None

    return {**filtros, "mes": list(range(1, hoje.month))}


def _separar_mes_em_andamento(consulta: dict, indicadores: list[str]) -> dict | None:
    """
    Indicadores com meta ("acumulado_so_meses_fechados"): o acumulado do
    ano atual usa só os meses fechados — senão a meta do mês INTEIRO entra
    contra poucos dias de venda. O mês em andamento é consultado à parte
    (resposta["mes_em_andamento"]). Só pro ano atual sozinho, sem agrupar
    por mês e sem comparação.
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

    return _com_meses_fechados(
        consulta, catalogo.INDICADORES[indicadores[0]],
        lambda anos, ano_atual: anos == [ano_atual],
    )


def _mesmos_meses_na_comparacao(consulta: dict, indicador_def: dict) -> dict | None:
    """
    Ano atual (incompleto) comparado com outro ano — "comparar_com" ou
    agrupando por 2+ anos — usa os mesmos meses fechados nos dois (antes
    eram 9 meses contra 12 e quase todas as filiais "caíam").
    """
    if indicador_def["granularidade_periodo"] != "mensal":
        return None

    def compara_anos(anos, ano_atual):
        return ano_atual in anos and bool(
            consulta.get("comparar_com")
            or ("ano" in (consulta.get("agrupar_por") or []) and len(anos) >= 2)
        )

    return _com_meses_fechados(consulta, indicador_def, compara_anos)


def _mes_atual_na_lista(resposta: dict) -> str | None:
    """"outubro de 2026" quando uma lista mês a mês inclui o mês atual (ele
    parecia "cair" 74% com poucos dias de venda)."""
    if "mes" not in (resposta.get("agrupar_por") or []):
        return None

    hoje = date.today()
    anos_filtro = [
        int(ano)
        for ano in _como_lista((resposta.get("filtros_aplicados") or {}).get("ano", []))
    ]

    for linha in resposta["resultados"]:
        ano = linha.get("ano")
        do_ano_atual = int(ano) == hoje.year if ano is not None else anos_filtro == [hoje.year]

        if do_ano_atual and str(linha.get("mes")) == str(hoje.month):
            return f"{_NOMES_MESES[hoje.month - 1]} de {hoje.year}"

    return None


# --- dados -------------------------------------------------------------------

def _aplicar_filtros(
    dados: pd.DataFrame, indicador_def: dict, filtros: dict
) -> tuple[pd.DataFrame, dict]:
    dimensoes = indicador_def["dimensoes"]
    resolvedores = indicador_def.get("resolver_dimensao", {})
    filtros_resolvidos: dict[str, list] = {}

    dimensoes_ordenadas = [
        dimensao for dimensao in _ORDEM_RESOLUCAO_DIMENSOES if dimensao in filtros
    ] + [
        dimensao for dimensao in filtros if dimensao not in _ORDEM_RESOLUCAO_DIMENSOES
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

        valores = _como_lista(valor)
        resolvedor = resolvedores.get(dimensao)

        if resolvedor:
            valores_resolvidos = []

            for item in valores:
                if dimensao in _RESOLVEDORES_COM_FILIAL:
                    encontrados = resolvedor(item, filiais=filtros_resolvidos.get("filial"))
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
    "RCA de uma filial" = quem tem meta cadastrada NAQUELA filial (contas
    genéricas também vendem, mas não são vendedores). Vale o par (filial,
    código): o mesmo código pode ter meta numa filial e ser conta genérica
    em outras (ex: código 1 tem meta só em Campos Sales). A referência é
    sempre a base de metas, qualquer que seja o indicador.

    Contas da empresa ("COMERCIAL FERRONORTE LTDA-F09-TIMON"...) têm meta
    (parte da meta da filial, rotina 8139), mas ficam fora das listas de
    RCA — pedidas pelo nome/código, continuam respondendo.
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
    rcas_validos: set | None = None,
    dimensoes_dos_campos: set | None = None,
) -> tuple[pd.DataFrame, set | None]:
    """
    Carrega o DataFrame do indicador (o arquivo certo pra dimensão pedida,
    ex: cliente ou produto) e aplica os filtros.

    Agrupado por "rca" sem RCA pedido (e "rca_requer_meta_cadastrada"):
    só RCAs com meta. `rcas_validos` vem pronto numa comparação de
    períodos — o conjunto tem que ser o MESMO nos dois lados, senão um
    RCA sem meta no ano anterior perdia o histórico e estragava o
    crescimento.
    """
    carregar = indicador_def.get("carregar")
    # Dimensões que escolhem o arquivo: as da pergunta e as que um campo
    # pedido precisa (ex: produtos diferentes → um arquivo com produto).
    da_fonte = {*agrupar_por, *filtros, *(dimensoes_dos_campos or ())}

    fontes = {
        fonte
        for dimensao, fonte in indicador_def.get("fontes_por_dimensao", {}).items()
        if dimensao in da_fonte
    }

    # Mais de um arquivo: vale o que também tem as dimensões dos outros
    # (ex: o de venda tem cliente — "vendas com mais desconto do Mateus"),
    # ou um arquivo que junta os dois ("fontes_combinadas", ex: cliente e
    # produto).
    if len(fontes) > 1:
        pedidas = {d for d in da_fonte if d in indicador_def.get("fontes_por_dimensao", {})}
        cobre_tudo = [
            fonte for fonte in [*fontes, *indicador_def.get("fontes_combinadas", ())]
            if pedidas <= {
                d for d, f in indicador_def["fontes_por_dimensao"].items() if f is fonte
            } | set(getattr(fonte, "tambem_tem", ()))
        ]
        fontes = set(cobre_tudo[:1]) or fontes

    # Cliente e produto vêm de arquivos diferentes (nenhum tem os dois).
    if len(fontes) > 1:
        raise ConsultaInvalida(
            "Ainda não dá pra combinar essas dimensões (ex: forma de pagamento "
            "com cliente) na mesma consulta — consulte uma de cada vez."
        )

    if fontes:
        carregar = fontes.pop()

    if carregar is None:
        raise ConsultaInvalida(
            "Esse indicador ainda não está conectado a uma fonte de "
            "dados real — não é possível buscar o valor pedido."
        )

    # Fonte que monta só o período pedido (ex: a foto dos clientes de cada
    # mês, que de uma vez dariam milhões de linhas) recebe os filtros.
    brutos = carregar(filtros) if getattr(carregar, "recebe_filtros", False) else carregar()

    # Ex: o arquivo do mix (cliente com produto) não tem RCA.
    sem_coluna = [
        dimensao for dimensao in dict.fromkeys([*agrupar_por, *filtros])
        if dimensao in indicador_def["dimensoes"] and indicador_def["dimensoes"][dimensao] not in brutos.columns
    ]

    if sem_coluna:
        pedidas = [d for d in dict.fromkeys([*agrupar_por, *filtros]) if d not in sem_coluna and d not in ("ano", "mes", "dia")]
        raise ConsultaInvalida(
            f"Não dá pra combinar {', '.join(sem_coluna)} com {', '.join(pedidas)} na mesma "
            f"consulta (os dados de {', '.join(pedidas)} não têm {', '.join(sem_coluna)}) — "
            "consulte um de cada vez."
        )

    dados, filtros_resolvidos = _aplicar_filtros(brutos, indicador_def, filtros)

    if (
        "rca" in agrupar_por
        and "rca" not in filtros
        and indicador_def.get("rca_requer_meta_cadastrada")
    ):
        if rcas_validos is None:
            rcas_validos = _rcas_com_meta_cadastrada(
                filtros_resolvidos.get("filial"), filtros_resolvidos.get("ano")
            )

        dimensoes = indicador_def["dimensoes"]
        chaves = pd.MultiIndex.from_arrays(
            [dados[dimensoes["filial"]], dados[dimensoes["rca"]]]
        )
        dados = dados[chaves.isin(rcas_validos)]

    return dados, rcas_validos, _tabela_da_filial(brutos, indicador_def, filtros_resolvidos)


def _campos_da_filial(indicador_def: dict) -> dict[str, tuple[str, tuple, set]]:
    """Campos "unico_por" com o período na chave (ex: o faturamento do mês
    da filial): valores da filial, não do item — {campo: (coluna, chave,
    colunas do período na chave)}."""
    periodo = {indicador_def["dimensoes"].get(dimensao) for dimensao in _DIMENSOES_DO_PERIODO}
    campos = {}

    for nome_campo, especificacao in indicador_def["campos"].items():
        coluna, agregacao, opcoes = _desempacotar_campo(especificacao)
        chave = opcoes.get("unico_por") or ()

        if agregacao == "sum" and not opcoes.get("foto_por") and periodo & set(chave):
            campos[nome_campo] = (coluna, chave, periodo & set(chave))

    return campos


def _tabela_da_filial(
    brutos: pd.DataFrame, indicador_def: dict, filtros_resolvidos: dict
) -> pd.DataFrame | None:
    """
    As linhas com os campos da filial, só com os filtros da chave deles
    (ex: filial e período): filtrado por RCA ou cliente, o faturamento da
    filial continua o do período inteiro, não só dos meses em que o item
    tem linha.
    """
    colunas = {coluna for _, chave, _ in _campos_da_filial(indicador_def).values() for coluna in chave}

    if not colunas:
        return None

    for dimensao, valores in filtros_resolvidos.items():
        coluna = indicador_def["dimensoes"].get(dimensao)

        if coluna in colunas:
            brutos = brutos[brutos[coluna].isin(valores)]

    return brutos


# --- agrupamento -------------------------------------------------------------

def _desempacotar_campo(especificacao) -> tuple[str, str, dict]:
    """
    Campo do catálogo: (coluna, agregação) ou (coluna, agregação, opções).
    A opção "unico_por" descarta linhas repetidas antes de somar — ex: a
    meta de tonelada da FILIAL aparece copiada em toda linha de RCA.
    A opção "foto_por" (ex: ("ANO", "MES")) é de campo que é uma FOTO num
    momento (ex: clientes ativos): num período de vários meses vale só o
    último, em vez de somar — ver _so_a_ultima_foto.
    """
    if len(especificacao) == 3:
        return especificacao

    coluna, agregacao = especificacao
    return coluna, agregacao, {}


def _particionar_campos_por_dedup(campos: dict) -> list[tuple[tuple, dict]]:
    """Agrupa os campos pelas opções ("unico_por", "foto_por"; None = sem):
    cada grupo é somado à parte e depois juntado."""
    grupos: dict[tuple, dict] = {}

    for nome_campo, especificacao in campos.items():
        coluna, agregacao, opcoes = _desempacotar_campo(especificacao)
        chave = (opcoes.get("unico_por"), opcoes.get("foto_por"))
        grupos.setdefault(chave, {})[nome_campo] = (coluna, agregacao)

    return list(grupos.items())


def _so_a_ultima_foto(
    dados: pd.DataFrame, colunas_agrupamento: list[str], foto_por: tuple
) -> pd.DataFrame:
    """
    Só as linhas do último momento (ex: ano/mês) do período: "clientes
    ativos em 2026" é a foto de outubro, não a soma dos 10 meses (o mesmo
    cliente contaria 10 vezes). Agrupado por mês ou ano, o último de cada
    grupo. É o último do período INTEIRO (não de cada filial/cliente): quem
    sumiu da foto mais nova não volta com uma foto antiga.
    """
    if dados.empty:
        return dados

    # ano/mês viram um número só (2026, 10 → 202610) pra achar o maior.
    momento = dados[foto_por[0]].astype("int64")

    for coluna in foto_por[1:]:
        momento = momento * 100 + dados[coluna].astype("int64")

    grupos = [coluna for coluna in colunas_agrupamento if coluna in foto_por]
    ultimo = momento.groupby([dados[coluna] for coluna in grupos]).transform("max") if grupos else momento.max()
    return dados[momento == ultimo]


def _campos_de_contagem(dados: pd.DataFrame, campos: dict) -> set[str]:
    """Campos somados (ou maior/menor) de coluna inteira (ex: nº de notas,
    dias sem comprar) e contagens de itens diferentes ("nunique", ex: nº de
    clientes) — continuam inteiros, em vez de "534.0"."""
    contagens = set()

    for nome_campo, especificacao in campos.items():
        coluna, agregacao, _ = _desempacotar_campo(especificacao)

        if agregacao == "nunique" or (
            agregacao in ("sum", "max", "min") and pd.api.types.is_integer_dtype(dados[coluna])
        ):
            contagens.add(nome_campo)

    return contagens


def _atributos_por_item(dados: pd.DataFrame, dimensao: str, coluna: str):
    """Nome/CNPJ/cidade de cada item da dimensão (ex: cliente), tirados do
    próprio arquivo — ({campo: coluna}, tabela) ou None se não houver."""
    atributos = {
        campo: coluna_df
        for campo, (coluna_df, _) in catalogo.ATRIBUTOS_DIMENSAO.get(dimensao, {}).items()
        if coluna_df in dados.columns
    }

    if not atributos:
        return None

    if catalogo.COLUNA_DO_MAIS_RECENTE in dados.columns:
        dados = dados.sort_values(catalogo.COLUNA_DO_MAIS_RECENTE, ascending=False)

    return atributos, dados.groupby(coluna)[list(atributos.values())].first()


def _sem_linhas_so_da_filial(
    dados: pd.DataFrame, campos: dict, colunas_agrupamento: list[str]
) -> pd.DataFrame:
    """
    Linha sem o item agrupado (ex: sem cliente) que só traz valor de um
    campo "unico_por" (ex: o faturamento do mês da filial, num mês sem
    título) não vira item ("nan") — ela existe pra esse valor entrar na
    filial/no total.
    """
    sem_item = dados[colunas_agrupamento].isna().any(axis=1)

    if not sem_item.any():
        return dados

    do_item = [
        coluna for coluna, _, opcoes in map(_desempacotar_campo, campos.values())
        if not opcoes.get("unico_por")
    ]
    vazia = dados[do_item].fillna(0).eq(0).all(axis=1)
    return dados[~(sem_item & vazia)]


def _valores_da_filial(
    dados: pd.DataFrame,
    colunas_agrupamento: list[str],
    coluna: str,
    chave: tuple,
    periodo: set,
    da_filial: pd.DataFrame,
) -> pd.Series:
    """
    Campo da filial (ver _campos_da_filial) de cada grupo: a soma do valor
    das filiais em que o grupo tem linha, no período inteiro da tabela da
    filial — ou só no mês/ano do grupo, quando agrupado por eles. Ex: o RCA
    com título só em março divide pelo faturamento da filial no ano todo.
    """
    tabela = da_filial.drop_duplicates(subset=list(chave))
    ligacao = [c for c in chave if c in colunas_agrupamento or c not in periodo]
    pares = dados[list(dict.fromkeys([*colunas_agrupamento, *ligacao]))].drop_duplicates()
    return (
        pares.merge(tabela[[*ligacao, coluna]], on=ligacao)
        .groupby(colunas_agrupamento, dropna=False)[coluna]
        .sum()
    )


def _aplicar_agrupamento(
    dados: pd.DataFrame,
    indicador_def: dict,
    agrupar_por: list[str],
    da_filial: pd.DataFrame | None = None,
) -> list[dict]:
    """
    Soma os campos por agrupamento. Sempre devolve uma LISTA (sem
    agrupamento, uma linha só com o total) — o resto do motor trabalha
    com um formato só.
    """
    # Campo cuja coluna o arquivo não tem fica de fora (ex: o faturamento
    # por produto não tem peso nem nº de notas) — em vez de dar erro.
    campos = {
        nome: especificacao
        for nome, especificacao in indicador_def["campos"].items()
        if _desempacotar_campo(especificacao)[0] in dados.columns
    }
    inteiros = _campos_de_contagem(dados, campos)
    medias = {nome for nome, especificacao in campos.items() if _desempacotar_campo(especificacao)[1] == "mean"}

    # Sem agrupamento: uma coluna constante, pra usar o mesmo caminho.
    if agrupar_por:
        colunas_agrupamento = [indicador_def["dimensoes"][d] for d in agrupar_por]
        dados = _sem_linhas_so_da_filial(dados, campos, colunas_agrupamento)
    else:
        dados = dados.assign(_total=0)
        colunas_agrupamento = ["_total"]

    tabelas_agregadas = []

    for (chave_dedup, foto_por), campos_do_grupo in _particionar_campos_por_dedup(campos):
        dados_do_grupo = (
            _so_a_ultima_foto(dados, colunas_agrupamento, foto_por) if foto_por else dados
        )
        # A duplicata é descartada DENTRO de cada grupo da consulta: no
        # DataFrame inteiro, agrupando por algo fora da chave (ex: rca),
        # só o primeiro item sobreviveria.
        if chave_dedup:
            dados_do_grupo = dados_do_grupo.drop_duplicates(
                subset=list(dict.fromkeys([*colunas_agrupamento, *chave_dedup]))
            )
        tabelas_agregadas.append(
            dados_do_grupo.groupby(colunas_agrupamento, dropna=False).agg(**campos_do_grupo)
        )

    agrupado = tabelas_agregadas[0]

    for tabela in tabelas_agregadas[1:]:
        agrupado = agrupado.join(tabela, how="outer")

    # Grupo que não aparece num dos lados do join: soma/contagem 0;
    # maior/menor/média fica vazio.
    if agrupar_por:
        agrupado = agrupado.fillna({
            nome: 0 for nome, especificacao in campos.items()
            if _desempacotar_campo(especificacao)[1] not in ("max", "min", "mean")
        })

    if da_filial is not None:
        for nome_campo, (coluna, chave, periodo) in _campos_da_filial(indicador_def).items():
            if nome_campo in campos:
                agrupado[nome_campo] = _valores_da_filial(
                    dados, colunas_agrupamento, coluna, chave, periodo, da_filial
                ).reindex(agrupado.index, fill_value=0)

    agrupado = agrupado.reset_index()
    resultados = []

    # Linha como dicionário (e não iterrows/Series): bem mais rápido em
    # listas grandes.
    for linha in agrupado.to_dict("records"):
        item = {}

        for dimensao, coluna in zip(agrupar_por, colunas_agrupamento):
            valor = linha[coluna]

            if dimensao in ("mes", "ano", "rca", "supervisor", "cliente", "produto", "venda"):
                # "rca" é código na maioria das bases, mas NOME na meta de
                # tonelada: tenta número, senão texto.
                try:
                    valor = int(valor)
                except (TypeError, ValueError):
                    valor = str(valor)
            elif dimensao == "dia":
                valor = valor.strftime("%Y-%m-%d") if hasattr(valor, "strftime") else str(valor)
            elif pd.isna(valor):
                valor = "Não informado"
            else:
                valor = str(valor)

            item[dimensao] = valor

        for nome_campo in campos:
            valor = linha[nome_campo]
            # Média de um item só (ex: a frequência de um cliente) é inteira:
            # "235 vezes", não "235.0".
            inteiro = nome_campo in inteiros or (nome_campo in medias and float(valor).is_integer())
            item[nome_campo] = None if pd.isna(valor) else _numero(valor, inteiro)

        resultados.append(item)

    for dimensao, coluna in zip(agrupar_por, colunas_agrupamento):
        encontrados = _atributos_por_item(dados, dimensao, coluna)

        if not encontrados:
            continue

        atributos, primeiro = encontrados
        por_item = primeiro.to_dict("index")

        for item in resultados:
            linha = por_item.get(item[dimensao])

            for campo, coluna_df in atributos.items():
                valor = None if linha is None else linha[coluna_df]
                item[campo] = None if pd.isna(valor) else str(valor)

    mapa_rca_nome_func = indicador_def.get("rca_nome_mapa")

    if "rca" in agrupar_por and mapa_rca_nome_func:
        mapa_rca_nome = mapa_rca_nome_func()

        for item in resultados:
            item["rca_nome"] = mapa_rca_nome.get(item["rca"])

    return resultados


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


def _itens_filtrados(dados: pd.DataFrame, indicador_def: dict, filtros: dict) -> dict:
    """Pra cada filtro numa dimensão com atributos (cliente, empresa), os
    itens que sobraram com nome/CNPJ — até 10 por dimensão."""
    itens = {}

    for dimensao in filtros:
        coluna = indicador_def["dimensoes"].get(dimensao)
        encontrados = coluna and _atributos_por_item(dados, dimensao, coluna)

        if not encontrados:
            continue

        atributos, primeiro = encontrados
        itens[dimensao] = [
            {
                dimensao: chave.item() if hasattr(chave, "item") else chave,
                **{
                    campo: None if pd.isna(linha[col]) else str(linha[col])
                    for campo, col in atributos.items()
                },
            }
            for chave, linha in primeiro.head(10).iterrows()
        ]

    return itens


# --- consulta ----------------------------------------------------------------

def _dimensoes_dos_campos(consulta: dict, indicador_def: dict) -> set:
    """As dimensões cujo arquivo os campos pedidos (colunas, ordem, filtros
    sobre a métrica, participação) precisam ("precisa_de")."""
    pedidos = {
        *(consulta.get("colunas") or []),
        (consulta.get("ordenar_por") or {}).get("campo"),
        (consulta.get("participacao") or {}).get("campo"),
        *(filtro.get("campo") for filtro in consulta.get("filtros_calculados") or []),
    }
    return {
        opcoes["precisa_de"]
        for nome, especificacao in indicador_def["campos"].items()
        if nome in pedidos and (opcoes := _desempacotar_campo(especificacao)[2]).get("precisa_de")
    }


def _colunas_do_item(
    dados: pd.DataFrame, indicador_def: dict, filtros: dict, agrupar_por: list[str]
) -> pd.DataFrame:
    """
    Campo com a opção "coluna_com" ((dimensão, coluna)) usa a outra coluna
    quando o item da consulta é a dimensão — agrupada por ela, ou filtrada
    sem agrupar pelo que o campo conta ("unico_por"). Ex: a frequência de
    uma empresa conta os dias em que QUALQUER loja dela comprou, não a
    média das lojas; agrupada por cliente, cada loja tem a sua.
    """
    trocas = {}

    for especificacao in indicador_def["campos"].values():
        coluna, _, opcoes = _desempacotar_campo(especificacao)

        if not opcoes.get("coluna_com") or opcoes["coluna_com"][1] not in dados.columns:
            continue

        dimensao, outra = opcoes["coluna_com"]
        mais_fina = any(
            indicador_def["dimensoes"].get(agrupada) in (opcoes.get("unico_por") or ())
            for agrupada in agrupar_por
        )

        if dimensao in agrupar_por or (dimensao in filtros and not mais_fina):
            trocas[coluna] = dados[outra]

    return dados.assign(**trocas) if trocas else dados


def _consultar_periodo(
    indicador_def: dict,
    consulta: dict,
    agrupar_por: list[str],
    rcas_validos: set | None = None,
    extras: dict | None = None,
) -> tuple[list[dict], set | None]:
    """
    Busca, agrupa e calcula os derivados de UM indicador no período da
    consulta. `extras`, quando informado, recebe:
    - "itens_filtrados": nome/CNPJ dos itens filtrados;
    - "total" (se `extras["calcular_total"]`): o total de todas as linhas
      — a IA nunca soma a lista de cabeça;
    - "totais_por_grupo" (se `extras["total_por"]`): o total de cada grupo,
      pra escolher os N maiores (ver _aplicar_ordenacao_por_grupo).
    """
    filtros = _filtros_efetivos(indicador_def, consulta)
    dados, rcas_validos, da_filial = buscar_dados_brutos(
        indicador_def, agrupar_por, filtros, rcas_validos, _dimensoes_dos_campos(consulta, indicador_def)
    )

    if dados.empty:
        return [], rcas_validos

    dados = _colunas_do_item(dados, indicador_def, filtros, agrupar_por)

    # Derivados (NPS, % de atingimento...) calculados em cada período,
    # antes de comparar — assim dá pra comparar os campos calculados.
    def agrupar(por: list[str]) -> list[dict]:
        return _sem_o_que_nao_fechou(
            _aplicar_derivados(_aplicar_agrupamento(dados, indicador_def, por, da_filial), indicador_def),
            indicador_def, por, filtros,
        )

    resultado = agrupar(agrupar_por)

    if extras is not None:
        extras["itens_filtrados"] = _itens_filtrados(dados, indicador_def, filtros)

        if agrupar_por and extras.get("calcular_total"):
            extras["total"] = agrupar([])[0]

        if extras.get("total_por"):
            extras["totais_por_grupo"] = agrupar([extras["total_por"]])

    # Código da filial em cada linha: sem ele a IA adivinha pelo nome e erra.
    if "filial" in agrupar_por:
        for linha in resultado:
            linha["codigo_filial"] = CODIGO_POR_NOME.get(linha["filial"])

    return resultado, rcas_validos


def _sem_o_que_nao_fechou(
    resultado: list[dict], indicador_def: dict, agrupar_por: list[str], filtros: dict
) -> list[dict]:
    """Campos com período próprio que fecha depois (ex: a inadimplência
    oficial): vazios, não zero, nas linhas só de meses ainda não fechados
    — senão a variação mostrava -100%."""
    proprio = indicador_def.get("periodo_dos_campos") or {}

    if "ultimo_mes_fechado" not in proprio:
        return resultado

    ultimo = proprio["ultimo_mes_fechado"]()
    anos = [int(ano) for ano in _como_lista(filtros.get("ano") or [])]
    meses = [int(mes) for mes in _como_lista(filtros.get("mes") or [])] or list(range(1, 13))

    for linha in resultado:
        anos_da_linha = [int(linha["ano"])] if "ano" in agrupar_por else anos
        meses_da_linha = [int(linha["mes"])] if "mes" in agrupar_por else meses

        if anos_da_linha and all((ano, mes) > ultimo for ano in anos_da_linha for mes in meses_da_linha):
            for campo in proprio["campos"]:
                if campo in linha:
                    linha[campo] = None

    return resultado


def _juntar_indicadores(
    resultado: list[dict],
    outro: list[dict],
    agrupar_por: list[str],
    campos_resultado: list[str],
    campos_outro: list[str],
) -> list[dict]:
    """Junta dois indicadores pela chave do agrupamento. Quem só existe num
    lado fica com os campos do outro vazios (a IA avisa que faltou dado)."""
    juntas = {
        _chave(linha, agrupar_por): {**dict.fromkeys(campos_outro), **linha}
        for linha in resultado
    }

    for linha in outro:
        juntas.setdefault(_chave(linha, agrupar_por), dict.fromkeys(campos_resultado)).update(linha)

    return [juntas[chave] for chave in sorted(juntas)]


def _consultar_indicadores(
    indicadores: list[str],
    consulta: dict,
    agrupar_por: list[str],
    rcas_validos: set | None = None,
    extras: dict | None = None,
) -> tuple[list[dict], set | None]:
    """O indicador principal e cada um de "cruzar_com" (mesmos filtros e
    período), juntados numa tabela só, com os derivados do cruzamento."""
    definicoes = [catalogo.INDICADORES[nome] for nome in indicadores]

    resultado, rcas_validos = _consultar_periodo(
        definicoes[0], consulta, agrupar_por, rcas_validos, extras
    )
    campos_resultado = _campos_do_indicador(definicoes[0])

    for definicao in definicoes[1:]:
        outro, _ = _consultar_periodo(definicao, consulta, agrupar_por)
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
    Junta o resultado com o da comparação (mesma chave), com diferença e
    percentual de cada campo (variacao_utils.calcular_diferenca_percentual).
    Período x período: só o que existe no atual. Item x item
    (`incluir_so_do_outro_lado`): o que só o outro lado tem também entra,
    ordenado pela chave.
    """
    mapa_anterior = {_chave(item, agrupar_por): item for item in anterior}

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

    resultados = [
        combinar(item, mapa_anterior.get(_chave(item, agrupar_por), {}), item)
        for item in atual
    ]

    if incluir_so_do_outro_lado:
        vistas = {_chave(item, agrupar_por) for item in atual}

        for chave_outra, item_anterior in mapa_anterior.items():
            if chave_outra not in vistas:
                base = {dimensao: item_anterior[dimensao] for dimensao in agrupar_por}
                resultados.append(combinar({}, item_anterior, {**dict.fromkeys(campos), **base}))

        resultados.sort(key=lambda item: _chave(item, agrupar_por))

    return resultados


def _aplicar_variacao_temporal(
    resultado: list[dict], agrupar_por: list[str], indicador_def: dict, filtros: dict
) -> list[dict]:
    """
    Agrupado por mês/ano, preenche a variação em relação ao período
    anterior (variacao_utils.calcular_variacao_sequencial), no campo
    "campo_variacao" (ou "campo_principal") do indicador:
    - "ano" com 2+ anos: cada ano contra o anterior (e, com "mes", cada mês
      contra o mesmo mês do ano anterior) — "..._ano_anterior";
    - só "mes", com 1 ano: cada mês contra o anterior — "..._mes_anterior".
    Os outros campos do indicador também ganham a variação, cada um com o
    seu nome ("percentual_{campo}_mes_anterior") — ex: ativos E inativos
    mês a mês, cada um com a sua.
    """
    campo = indicador_def.get("campo_variacao") or indicador_def.get("campo_principal")

    if not campo or not resultado or not {"mes", "ano"} & set(agrupar_por):
        return resultado

    campos = [
        nome
        for nome in (*indicador_def["campos"], *(d["nome"] for d in indicador_def.get("derivados", [])))
        if nome in resultado[0]
    ]

    dimensoes_extras = [d for d in agrupar_por if d not in ("mes", "ano")]
    anos = filtros.get("ano")
    anos = anos if isinstance(anos, list) else None

    def extras(item):
        return tuple(item[dimensao] for dimensao in dimensoes_extras)

    if "ano" in agrupar_por and anos and len(anos) >= 2:
        posicao_do_ano = {ano: indice for indice, ano in enumerate(anos)}

        def grupo(item):
            return extras(item), item["mes"] if "mes" in agrupar_por else None

        sufixo, chave_grupo = "ano_anterior", grupo
        chave_ordem = lambda item: (grupo(item), posicao_do_ano.get(item["ano"], len(anos)))
        calcular_variacao_sequencial(
            resultado,
            campo_valor=campo,
            sufixo=sufixo,
            chave_grupo=chave_grupo,
            chave_ordem=chave_ordem,
            incluir_valor_anterior_como=f"{campo}_ano_anterior",
        )
    elif "mes" in agrupar_por and "ano" not in agrupar_por and anos and len(anos) == 1:
        sufixo, chave_grupo = "mes_anterior", extras
        chave_ordem = lambda item: (extras(item), item["mes"])
        calcular_variacao_sequencial(
            resultado,
            campo_valor=campo,
            sufixo=sufixo,
            chave_grupo=chave_grupo,
            chave_ordem=chave_ordem,
        )
    else:
        return resultado

    for outro in campos:
        calcular_variacao_sequencial(
            resultado,
            campo_valor=outro,
            sufixo=f"{outro}_{sufixo}",
            chave_grupo=chave_grupo,
        )

    return resultado


def _aplicar_necessidade_diaria(
    resultado: list[dict], agrupar_por: list[str], indicador_def: dict, filtros: dict
) -> list[dict]:
    """Quanto falta vender por dia útil restante: indicador de meta, sem
    agrupamento, um mês e um ano só (e só tem dias restantes no mês atual)."""
    campo_faltante = indicador_def.get("necessidade_diaria_campo")
    meses, anos = filtros.get("mes"), filtros.get("ano")

    if (
        not campo_faltante or agrupar_por or not resultado
        or not (isinstance(meses, list) and isinstance(anos, list))
        or len(meses) != 1 or len(anos) != 1
    ):
        return resultado

    dias_restantes = motor_metricas.calcular_dias_uteis_restantes(anos[0], meses[0])

    if dias_restantes:
        resultado[0]["necessidade_diaria"] = motor_metricas.calcular_necessidade_diaria(
            resultado[0].get(campo_faltante), dias_restantes
        )

    return resultado


def _aplicar_filtro_calculado(resultado: list[dict], filtro: dict) -> list[dict]:
    operador = _OPERADORES.get(filtro["operador"])

    if operador is None:
        raise ConsultaInvalida(
            f"Operador '{filtro['operador']}' não é suportado em filtros_calculados."
        )

    campo = filtro["campo"]

    return [
        item for item in resultado
        if item.get(campo) is not None and operador(item[campo], filtro["valor"])
    ]


# --- ordenação ---------------------------------------------------------------

def _aplicar_ordenacao(resultado: list[dict], ordenar_por: dict | None) -> list[dict]:
    """
    Ordena por um campo e corta nos N primeiros — "os N maiores" sai exato
    daqui, sem a IA comparar uma lista "de olho". Itens sem valor no campo
    ficam de fora.
    """
    if not ordenar_por or not resultado:
        return resultado

    campo = ordenar_por["campo"]
    itens_ordenados = sorted(
        (item for item in resultado if item.get(campo) is not None),
        key=lambda item: item[campo],
        reverse=ordenar_por.get("ordem", "desc") != "asc",
    )

    limite = ordenar_por.get("limite")
    return itens_ordenados[:limite] if limite else itens_ordenados


def _aplicar_ordenacao_por_grupo(
    resultado: list[dict], ordenar_por: dict, grupos: list
) -> list[dict]:
    """
    "Os N maiores e os principais de cada" (ex: os 5 RCAs com mais desconto
    e os 3 clientes de cada): `grupos` já vem na ordem do total de cada
    grupo; as linhas de cada um são ordenadas e cortadas em "limite".
    Sem "limite", ficam na ordem natural (janeiro → dezembro).
    """
    grupo = ordenar_por["por"]
    limite = ordenar_por.get("limite")
    ordem_do_grupo = {
        "campo": ordenar_por["campo"],
        "ordem": ordenar_por.get("ordem", "desc"),
        "limite": limite,
    }

    def linhas_do_grupo(valor):
        linhas = [item for item in resultado if item.get(grupo) == valor]
        return _aplicar_ordenacao(linhas, ordem_do_grupo) if limite else linhas

    return [linha for valor in grupos for linha in linhas_do_grupo(valor)]


def _separar_sem_valor(
    resultado: list[dict], indicadores: list[dict], ordenar_por: dict | None,
    agrupar_por: list[str] | None = None,
) -> tuple[list[dict], dict | None]:
    """
    "Quem MENOS…": quem não teve o que está sendo medido sai da lista e vem
    à parte, pela regra "menor_ignora" do indicador do campo ordenado (ex:
    "quem menos deu desconto" sem quem deu R$ 0,00; "quem menos faturou"
    sem o RCA que só tem meta cadastrada e não vendeu nada). Só muda a
    LISTA — os totais somam tudo, iguais ao WinThor. O motivo muda com o
    que está sendo listado ("motivo_por_dimensao"): o RCA "tem meta, mas
    não vendeu"; o cliente "não comprou, só devolveu".
    """
    if not ordenar_por or ordenar_por.get("ordem") != "asc" or ordenar_por.get("por"):
        return resultado, None

    regra = next(
        (
            definicao["menor_ignora"] for definicao in indicadores
            if ordenar_por.get("campo") in (definicao.get("menor_ignora") or {}).get("ordem_por", ())
        ),
        None,
    )

    if not regra or not resultado or regra["campo"] not in resultado[0]:
        return resultado, None

    motivo = next(
        (
            regra["motivo_por_dimensao"][dimensao] for dimensao in agrupar_por or []
            if dimensao in regra.get("motivo_por_dimensao", {})
        ),
        regra["motivo"],
    )
    # Cada grupo à parte com o seu motivo: o principal e os de "tambem" (ex:
    # faturamento negativo = "devolveu mais do que comprou").
    grupos = [
        {"campo": regra["campo"], "abaixo_de": regra["abaixo_de"], "motivo": motivo},
        *regra.get("tambem", []),
    ]

    def nome(linha):
        return next((str(linha[c]) for c in _CAMPOS_DE_NOME if linha.get(c) is not None), "")

    a_parte = []

    for grupo in grupos:
        # Grupo só de uma ordem (ex: negativo só ordenando pelo faturamento;
        # pela venda bruta, quem comprou R$ 1.122 e devolveu mais fica).
        if ordenar_por["campo"] not in grupo.get("ordem_por", (ordenar_por["campo"],)):
            continue

        fora = [
            linha for linha in resultado
            if grupo["campo"] in linha and (linha[grupo["campo"]] or 0) < grupo["abaixo_de"]
        ]

        if fora:
            tirados = {id(linha) for linha in fora}
            resultado = [linha for linha in resultado if id(linha) not in tirados]
            a_parte.append({
                "quantidade": len(fora),
                "itens": [nome(linha) for linha in fora[:20]],
                "motivo": grupo["motivo"] + "; ficaram fora da lista de 'menor'.",
            })

    if not a_parte:
        return resultado, None

    principal, *outros = a_parte
    return resultado, {**principal, "tambem_fora": outros} if outros else principal


# --- tabela da tela ----------------------------------------------------------

def _linhas_da_tabela(
    resultado: list[dict],
    colunas: list[str],
    rotulos: dict | None = None,
    comparar: list[str] | None = None,
    pela_resposta: dict | None = None,
) -> list[dict]:
    """
    Linhas da tabela da tela: a identificação (filial, mês...), as colunas
    pedidas e a comparação delas (`comparar`; padrão: todas). A IA continua
    recebendo o resultado completo. "_colunas_pedidas" avisa a tela de que
    a escolha foi feita aqui (ui/formatacao.preparar_tabela); "_rotulos"
    troca títulos (ex: os nomes das duas filiais). "_pela_resposta": as
    colunas que a tela troca pelas que a resposta cita ("opcionais") e as
    que ela pode acrescentar ("extras").
    """
    comparacoes = {
        nome
        for coluna in (colunas if comparar is None else comparar)
        for nome in (f"{coluna}_anterior", f"diferenca_{coluna}", f"percentual_{coluna}")
    }
    fixas = {*catalogo.DIMENSOES_VALIDAS, "rca_nome", *_CAMPOS_DE_ATRIBUTO}

    extras = set((pela_resposta or {}).get("extras", []))

    def manter(chave: str) -> bool:
        return (
            chave in fixas or chave in colunas or chave in comparacoes or chave in extras
            or chave.endswith(("_mes_anterior", "_ano_anterior"))
        )

    return [
        {
            **{chave: valor for chave, valor in linha.items() if manter(chave)},
            "_colunas_pedidas": colunas,
            **({"_rotulos": rotulos} if rotulos else {}),
            **({"_pela_resposta": pela_resposta} if pela_resposta else {}),
        }
        for linha in resultado
    ]


def _campos_da_ordem_e_dos_filtros(consulta: dict) -> list[str]:
    return [
        (consulta.get("ordenar_por") or {}).get("campo"),
        *(filtro.get("campo") for filtro in consulta.get("filtros_calculados") or []),
    ]


def _colunas_usadas_na_pergunta(consulta: dict, indicador_def: dict) -> list[str] | None:
    """
    Sem "colunas" da IA, a tabela mostra só o que a pergunta usou: o campo
    da ordem, os dos filtros calculados e, num cruzamento, o principal de
    cada indicador — ou as "colunas_no_cruzamento" dele (desconto: R$ e %).
    """
    campos = _campos_da_ordem_e_dos_filtros(consulta)

    if consulta.get("cruzar_com"):
        for nome in [consulta["indicador"], *consulta["cruzar_com"]]:
            definicao = catalogo.INDICADORES[nome]
            campos += definicao.get("colunas_no_cruzamento") or [definicao.get("campo_principal")]

    if not any(campos):
        return None

    return list(dict.fromkeys(campo for campo in campos if campo))


def _colunas_da_comparacao_de_periodos(
    colunas: list[str], indicadores: list[str], atual: str, anterior: str
) -> tuple[list[str], dict]:
    """
    Comparação de períodos que qualquer um entende: o campo do foco nos
    DOIS períodos (com o período no título) e quanto cresceu/caiu; os
    outros campos com o período atual entre parênteses.
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
        rotulos.setdefault(campo, f"{_rotulo_do_campo(campo, indicadores)} ({atual})")

    return novas, rotulos


def _nome_do_lado(indicador_def: dict, filtros: dict, dimensoes: list[str]) -> str:
    """Nome legível de um lado da comparação entre itens (ex: "TIMON")."""
    partes = []

    for dimensao in dimensoes:
        valores = filtros.get(dimensao)

        if not valores:
            partes.append("GERAL")
            continue

        resolvedor = indicador_def.get("resolver_dimensao", {}).get(dimensao)

        for valor in _como_lista(valores):
            try:
                nome = resolvedor(valor) if resolvedor and dimensao in ("filial", "estado") else valor
            except ValueError:
                nome = valor

            partes.append(str(nome))

    return " + ".join(partes)


# --- executar_consulta, em etapas ----------------------------------------------

def _preparar_consulta(consulta: dict) -> dict:
    consulta = _normalizar_comparacoes(consulta)

    # Dimensão em "colunas" (a IA às vezes pede "rca") já sai sempre na
    # tabela quando é agrupada: é descartada em vez de derrubar a consulta.
    if consulta.get("colunas"):
        fixas = (*catalogo.DIMENSOES_VALIDAS, "rca_nome", *_CAMPOS_DE_ATRIBUTO)
        consulta = {
            **consulta,
            "colunas": [coluna for coluna in consulta["colunas"] if coluna not in fixas],
        }

    consulta = _sem_ordem_por_contagem(consulta)
    validar_consulta(consulta)
    return consulta


# Sem período na pergunta, o "atual" de cada comparação.
_PERIODO_DA_COMPARACAO = {
    "ontem": "hoje",
    "semana_anterior": "semana_atual",
    "mes_anterior": "mes_atual",
    "mesmo_mes_ano_anterior": "mes_atual",
    "ano_anterior": "ano_atual",
}


def _mudar_mes(dia: date, meses: int, fim_do_mes: bool = False) -> date:
    """O mesmo dia `meses` meses antes/depois (29/02 → 28/02); com
    `fim_do_mes`, o último dia do mês de destino."""
    ano, mes = divmod(dia.year * 12 + dia.month - 1 + meses, 12)
    ultimo = calendar.monthrange(ano, mes + 1)[1]
    return date(ano, mes + 1, ultimo if fim_do_mes else min(dia.day, ultimo))


def _anterior_ao_periodo(comparar_com: str, filtros: dict) -> dict:
    """
    O período "anterior" contado a partir do período consultado, como
    comparar_com_personalizado: agosto/2024 x "mes_anterior" = julho/2024;
    2025 x "ano_anterior" = 2024.
    """
    if "dia" in filtros:
        inicio, fim = _inicio_e_fim(filtros["dia"])
        fim_do_mes = fim == _mudar_mes(fim, 0, fim_do_mes=True)

        if comparar_com == "ontem":
            tamanho = timedelta(days=(fim - inicio).days + 1)
            inicio, fim = inicio - tamanho, fim - tamanho
        elif comparar_com == "semana_anterior":
            inicio, fim = inicio - timedelta(days=7), fim - timedelta(days=7)
        else:
            meses = -1 if comparar_com == "mes_anterior" else -12
            inicio, fim = _mudar_mes(inicio, meses), _mudar_mes(fim, meses, fim_do_mes)

        return {"data_inicial": inicio.isoformat(), "data_final": fim.isoformat()}

    anos = sorted(int(ano) for ano in _como_lista(filtros.get("ano", [])))
    meses = sorted(int(mes) for mes in _como_lista(filtros.get("mes", [])))

    if comparar_com in ("ano_anterior", "mesmo_mes_ano_anterior"):
        return {"anos": [ano - 1 for ano in anos], **({"meses": meses} if meses else {})}

    # "mes_anterior": os mesmos N meses seguidos, logo antes (dentro de um ano).
    seguidos = meses and meses == list(range(meses[0], meses[-1] + 1))
    primeiro = date(anos[0], meses[0], 1) if seguidos and len(anos) == 1 else None
    antes = [_mudar_mes(primeiro, -n) for n in range(len(meses), 0, -1)] if primeiro else []

    if not antes or len({dia.year for dia in antes}) > 1:
        raise ConsultaInvalida(
            "Não dá pra saber qual é o 'mês anterior' desse período — use "
            "comparar_com 'personalizado' com o período exato da comparação."
        )

    return {"meses": [dia.month for dia in antes], "anos": [antes[0].year]}


def _comparacao_a_partir_do_periodo(consulta: dict, indicador_def: dict) -> dict:
    """
    Período definido na pergunta (filtros ou "personalizado") + "comparar_com"
    relativo (mês/ano anterior, ontem…): o anterior é o do período pedido,
    não o de hoje. Sem período definido, vale o de hoje (_PERIODO_DA_COMPARACAO).
    """
    comparar_com = consulta.get("comparar_com")

    if comparar_com not in _PERIODO_DA_COMPARACAO or consulta.get("periodo") not in (None, "personalizado"):
        return consulta

    filtros = _filtros_efetivos(indicador_def, consulta)

    if not {"ano", "dia"} & set(filtros):
        return consulta

    return {
        **consulta,
        "comparar_com": "personalizado",
        "comparar_com_personalizado": _anterior_ao_periodo(comparar_com, filtros),
    }


def _ajustar_periodo(consulta: dict, indicador_def: dict) -> tuple[dict, dict]:
    """
    Os ajustes de período antes de consultar. Devolve a consulta ajustada e
    o contexto pra resposta: período consultado, se foi assumido, se usou
    os mesmos meses nos anos e o parcial do mês em andamento.
    """
    indicadores = [consulta["indicador"], *(consulta.get("cruzar_com") or [])]
    consulta = _comparacao_a_partir_do_periodo(consulta, indicador_def)
    periodo_consultado = _descrever_periodo(_filtros_efetivos(indicador_def, consulta))

    # Sem período, vale o "periodo_padrao" de qualquer indicador da consulta
    # (o ano atual), em vez de somar todo o histórico desde 2020.
    periodo_padrao = next(
        (
            catalogo.INDICADORES[nome]["periodo_padrao"]
            for nome in indicadores
            if catalogo.INDICADORES[nome].get("periodo_padrao")
        ),
        None,
    )
    # Filtro que já tem data própria (ex: uma venda) dispensa o padrão.
    if any(
        dimensao in (consulta.get("filtros") or {})
        for nome in indicadores
        for dimensao in catalogo.INDICADORES[nome].get("sem_periodo_padrao_com", ())
    ):
        periodo_padrao = None

    # "comparado ao mês anterior" sem dizer o período = este mês x o
    # anterior.
    periodo_da_comparacao = _PERIODO_DA_COMPARACAO.get(consulta.get("comparar_com"))

    if periodo_consultado is None and periodo_da_comparacao:
        periodo_padrao = periodo_da_comparacao

    periodo_assumido = periodo_consultado is None and periodo_padrao is not None

    if periodo_assumido:
        consulta = {**consulta, "periodo": periodo_padrao, "periodo_personalizado": None}
        periodo_consultado = _descrever_periodo(_filtros_efetivos(indicador_def, consulta))

    filtros_mesmos_meses = _mesmos_meses_na_comparacao(consulta, indicador_def)

    if filtros_mesmos_meses is not None:
        consulta = _com_filtros(consulta, filtros_mesmos_meses)
        periodo_consultado = _descrever_periodo(filtros_mesmos_meses)

    filtros_meses_fechados = _separar_mes_em_andamento(consulta, indicadores)
    mes_em_andamento = None

    if filtros_meses_fechados is not None:
        hoje = date.today()
        # Sem ordenar/limite: o parcial mostra os MESMOS itens do resultado
        # principal (filtrado na resposta), não o "top N" do mês.
        parcial = executar_consulta({
            **_com_filtros(consulta, {**filtros_meses_fechados, "mes": [hoje.month]}),
            "ordenar_por": None,
        })
        mes_em_andamento = {
            "descricao": (
                f"{parcial['periodo_consultado']['descricao']} — mês em "
                f"andamento, com vendas até {hoje.strftime('%d/%m/%Y')}"
            ),
            "resultados": parcial["resultados"],
        }
        consulta = _com_filtros(consulta, filtros_meses_fechados)
        periodo_consultado = _descrever_periodo(filtros_meses_fechados)

    # Agrupada por 2+ anos, a variação de um ano pro outro já vem pronta;
    # um "comparar_com" a mais comparava cada ano com ele mesmo.
    anos_consultados = _como_lista((periodo_consultado or {}).get("ano", []))

    if (
        consulta.get("comparar_com") and "ano" in (consulta.get("agrupar_por") or [])
        and len(anos_consultados) >= 2
    ):
        consulta = {**consulta, "comparar_com": None, "comparar_com_personalizado": None}

    return consulta, {
        "periodo_consultado": periodo_consultado,
        "periodo_assumido": periodo_assumido,
        "mesmos_meses": filtros_mesmos_meses is not None,
        "mes_em_andamento": mes_em_andamento,
    }


def _consultar(consulta: dict, indicador_def: dict) -> tuple[list[dict], dict, tuple | None]:
    """
    Busca os dados (com cruzamento) e aplica a comparação, a variação no
    tempo e os filtros sobre a métrica. Devolve o resultado, os extras
    (totais, itens filtrados) e os nomes dos lados de uma comparação entre
    itens.
    """
    indicadores = [consulta["indicador"], *(consulta.get("cruzar_com") or [])]
    agrupar_por = consulta.get("agrupar_por") or []
    cruzar_com = consulta.get("cruzar_com")
    comparar_com = consulta.get("comparar_com")
    comparar_filtros = consulta.get("comparar_filtros")
    lados = None

    # Total de todas as linhas: só na consulta simples (comparação e filtro
    # sobre a métrica deixariam o total diferente das linhas mostradas).
    extras = {
        "calcular_total": not (
            cruzar_com or comparar_com or comparar_filtros
            or consulta.get("filtros_calculados")
        ),
        "total_por": (consulta.get("ordenar_por") or {}).get("por"),
    }

    resultado, rcas_validos = _consultar_indicadores(
        indicadores, consulta, agrupar_por, extras=extras
    )

    # Total da consulta cruzada: a mesma consulta sem agrupar (sem ele a IA
    # somava só as 60 linhas que recebe). Por RCA, não: a lista é só de
    # quem tem meta, o total sem agrupar não seria a soma dela.
    if (
        cruzar_com and agrupar_por and not comparar_com and not comparar_filtros
        and not consulta.get("filtros_calculados") and "rca" not in agrupar_por
    ):
        total, _ = _consultar_indicadores(indicadores, consulta, [], rcas_validos=rcas_validos)

        if total:
            extras["total"] = total[0]

    if comparar_com:
        # Mesmos RCAs válidos do período principal (ver buscar_dados_brutos).
        resultado_comparacao, _ = _consultar_indicadores(
            indicadores, _do_periodo_comparado(consulta), agrupar_por,
            rcas_validos=rcas_validos,
        )
        # Período principal sem dado (ex: um domingo): mostra o outro lado
        # com o principal vazio, em vez de descartar a comparação.
        resultado = _combinar_comparacao(
            resultado, resultado_comparacao, agrupar_por,
            _campos_da_consulta(indicadores), incluir_so_do_outro_lado=not resultado,
        )
    elif comparar_filtros:
        # Item x item (ex: filial A x B): a mesma consulta com os filtros
        # trocados. O lado A é o valor, o lado B o "_anterior".
        filtros_b = {**(consulta.get("filtros") or {}), **comparar_filtros}
        resultado_b, _ = _consultar_indicadores(
            indicadores, {**consulta, "filtros": filtros_b}, agrupar_por
        )
        resultado = _combinar_comparacao(
            resultado, resultado_b, agrupar_por, _campos_da_consulta(indicadores),
            incluir_so_do_outro_lado=True,
        )
        lados = (
            _nome_do_lado(indicador_def, consulta.get("filtros") or {}, list(comparar_filtros)),
            _nome_do_lado(indicador_def, filtros_b, list(comparar_filtros)),
        )
    elif not cruzar_com:
        # Variação no tempo e necessidade diária são do indicador principal
        # (num cruzamento ficariam ambíguas).
        filtros = _filtros_efetivos(indicador_def, consulta)
        resultado = _aplicar_variacao_temporal(resultado, agrupar_por, indicador_def, filtros)
        resultado = _aplicar_necessidade_diaria(resultado, agrupar_por, indicador_def, filtros)

    filtros_calculados = consulta.get("filtros_calculados") or []
    antes_do_filtro = resultado

    if filtros_calculados:
        # Quantos havia antes do filtro, pra resposta dizer "10 de 18".
        extras["itens_antes_do_filtro"] = len(resultado)

    for filtro_calculado in filtros_calculados:
        resultado = _aplicar_filtro_calculado(resultado, filtro_calculado)

    # Nenhum item atendeu a todas as condições: quem chegou mais perto
    # (todas menos uma), pra resposta não parar no "nenhuma".
    if not resultado and len(filtros_calculados) > 1:
        extras["mais_perto_do_filtro"] = _mais_perto_do_filtro(antes_do_filtro, filtros_calculados)

    return resultado, extras, lados


def _mais_perto_do_filtro(resultado: list[dict], filtros_calculados: list[dict]) -> list[dict]:
    """Os itens que atendem a todas as condições menos uma, com a que faltou."""
    perto = []

    for item in resultado:
        faltaram = [
            filtro for filtro in filtros_calculados
            if not _aplicar_filtro_calculado([item], filtro)
        ]

        if len(faltaram) == 1:
            perto.append({
                **item,
                "condicao_que_faltou": (
                    f"{faltaram[0]['campo']} {faltaram[0]['operador']} {faltaram[0]['valor']}"
                ),
            })

    return perto


def _ordenar(resultado: list[dict], ordenar_por: dict | None, extras: dict) -> tuple[list[dict], list | None]:
    """Ordena e corta; com "por", escolhe os grupos pelo total de CADA
    GRUPO (assim um % também ordena certo) e corta dentro de cada um."""
    if not (ordenar_por and ordenar_por.get("por")):
        return _aplicar_ordenacao(resultado, ordenar_por), None

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

    return resultado, totais_por_grupo


def _avisos_para_a_ia(
    resposta: dict, consulta: dict, indicador_def: dict, contexto: dict,
    extras: dict, resultado_antes_do_limite: list[dict],
) -> None:
    """Os campos de aviso da resposta — cada um diz à IA o que contar."""
    agrupar_por = consulta.get("agrupar_por") or []
    indicadores = [consulta["indicador"], *(consulta.get("cruzar_com") or [])]
    ordenar_por = consulta.get("ordenar_por")

    # Campo com período próprio (ex: a frequência de compra): as datas que
    # ele usou, prontas.
    proprio = indicador_def.get("periodo_dos_campos")
    # Ordenada/filtrada por um campo vazio (ex: mês ainda não fechado), a
    # lista sai vazia — o aviso diz o porquê.
    pedidos = {
        (ordenar_por or {}).get("campo"),
        *(filtro.get("campo") for filtro in consulta.get("filtros_calculados") or []),
    }

    if proprio and (
        any(campo in linha for linha in resposta["resultados"][:1] for campo in proprio["campos"])
        or pedidos & set(proprio["campos"])
    ):
        resposta[proprio["aviso"]] = proprio["descrever"](_filtros_efetivos(indicador_def, consulta))

    if contexto["mesmos_meses"]:
        resposta["mesmo_periodo_nos_anos"] = (
            "O ano atual ainda não terminou: a comparação usa os mesmos meses "
            "fechados nos anos comparados. Diga isso na resposta (ex: "
            "\"comparando janeiro a setembro de 2025 e de 2026\")."
        )

    if ordenar_por and ordenar_por.get("campo"):
        # Diz por qual campo a lista foi ordenada (R$ ou %).
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

    # O "como ler" de cada indicador vai junto do resultado: quem ESCREVE a
    # resposta (a 2ª chamada da IA) não vê a descrição da ferramenta, que só
    # a 1ª chamada (a que monta a consulta) lê.
    como_ler = {
        nome: catalogo.INDICADORES[nome]["como_ler"]
        for nome in indicadores if catalogo.INDICADORES[nome].get("como_ler")
    }

    if como_ler:
        resposta["como_ler_o_indicador"] = como_ler

    foto = _momento_da_foto(indicadores, agrupar_por, contexto["periodo_consultado"])

    if foto:
        fotos, quando = foto
        resposta["situacao_na_data"] = (
            f"{_juntar_com_e(fotos)} são a situação {quando}, não a soma do "
            "período; os outros campos juntam o período todo. Diga essa data "
            "na resposta."
        )

    if contexto["periodo_assumido"]:
        periodo = contexto["periodo_consultado"]["descricao"]
        # Num indicador "foto" (ex: clientes), vale a situação na data.
        usado = (
            f"a situação {foto[1]} (os outros campos são de {periodo})"
            if foto else periodo
        )
        # Campo com período próprio (ex: a frequência): as datas dele.
        proprio = indicador_def.get("periodo_dos_campos")

        if proprio and proprio["aviso"] in resposta:
            usado += f"; {proprio['nome']} usa {resposta[proprio['aviso']]}"

        resposta["periodo_assumido"] = (
            f"A pergunta não disse o período: vale {usado}. Diga só o período "
            "do número que a resposta usa e que dá pra consultar outro período."
        )

    if contexto["mes_em_andamento"] is not None:
        mostradas = {_chave(linha, agrupar_por) for linha in resposta["resultados"]}
        resposta["mes_em_andamento"] = {
            **contexto["mes_em_andamento"],
            "resultados": [
                linha for linha in contexto["mes_em_andamento"]["resultados"]
                if _chave(linha, agrupar_por) in mostradas
            ],
        }

    if "itens_antes_do_filtro" in extras:
        # Texto pronto, sem os nomes internos dos campos.
        resposta["quantidade_antes_do_filtro"] = (
            f"{len(resultado_antes_do_limite)} passaram no filtro, de "
            f"{extras['itens_antes_do_filtro']} consultados no total. Diga os dois "
            "números, cada um com o nome do que conta (ex: \"10 das 18 filiais\", "
            "\"52 clientes novos, de 5.075 clientes do RCA\")."
        )

    if extras.get("mais_perto_do_filtro"):
        resposta["mais_perto_do_filtro"] = {
            "como_ler": (
                "Nenhum item atendeu a TODAS as condições. Estes atendem a "
                "todas menos uma ('condicao_que_faltou'): depois de dizer "
                "'nenhuma', mostre-os como os que chegaram mais perto, com o "
                "número da condição que faltou."
            ),
            "itens": extras["mais_perto_do_filtro"],
        }

    if extras.get("itens_filtrados"):
        resposta["itens_filtrados"] = extras["itens_filtrados"]

    if extras.get("total"):
        resposta["total_de_todas_as_linhas"] = {
            **extras["total"],
            "quantidade_de_linhas": len(resultado_antes_do_limite),
            # ex: 149 linhas = 37 lojas x 2 anos — não são "149 lojas".
            "quantidade_por_dimensao": {
                dimensao: len({linha.get(dimensao) for linha in resultado_antes_do_limite})
                for dimensao in agrupar_por
            },
        }

        # Lista de RCAs = só vendedores com meta: a soma NÃO é o total da
        # filial do WinThor (que tem contas da empresa e canal único).
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


def _lista_de_itens(indicador_def: dict, consulta: dict, resultado: list[dict]) -> dict | None:
    """
    A opção "lista_de_itens" do indicador (ex: clientes), quando a consulta
    é uma lista dessa dimensão — agrupada só por ela, sem mês/ano (aí a
    ordem natural é a do tempo).
    """
    lista = indicador_def.get("lista_de_itens")

    if not lista or not resultado or (consulta.get("agrupar_por") or []) != [lista["dimensao"]]:
        return None

    return lista


def _avisos_da_lista(
    resposta: dict, lista: dict, consulta: dict, resultado_antes_do_limite: list[dict]
) -> None:
    """Quantos de TODA a lista em cada valor de "resumir_por" (ex: situação)
    e, sem ordem pedida, a ordem usada — a IA só vê os primeiros itens."""
    indicadores = [consulta["indicador"], *(consulta.get("cruzar_com") or [])]
    resumir_por = lista.get("resumir_por")

    if resumir_por and resumir_por in resultado_antes_do_limite[0]:
        quantos: dict[str, int] = {}

        for linha in resultado_antes_do_limite:
            valor = str(linha.get(resumir_por))
            quantos[valor] = quantos.get(valor, 0) + 1

        rotulo = catalogo.ATRIBUTOS_DIMENSAO[lista["dimensao"]][resumir_por][1].lower()
        resposta[f"quantos_por_{resumir_por}"] = {
            "como_ler": (
                f"Quantos da lista INTEIRA ({len(resultado_antes_do_limite)}) "
                f"em cada {rotulo}. Com mais de uma, diga o total e logo em "
                "seguida quantos em cada uma — não deixe o total parecer de "
                "uma só."
            ),
            "quantidade": dict(sorted(quantos.items(), key=lambda item: -item[1])),
        }

    if lista.get("ordem") and not consulta.get("ordenar_por"):
        campo, ordem = lista["ordem"]
        sentido = "do menor para o maior" if ordem == "asc" else "do maior para o menor"
        resposta["criterio_da_ordem"] = (
            f"Sem ordem pedida: a lista vem por {_rotulo_do_campo(campo, indicadores).lower()}, "
            f"{sentido}. Se citar exemplos, diga essa ordem."
        )


def _momento_da_foto(
    indicadores: list[str], agrupar_por: list[str], periodo: dict | None
) -> tuple[list[str], str] | None:
    """
    Campos "foto" (ex: clientes ativos) não somam o período: dizem a
    situação no último dia dele. Devolve os rótulos desses campos e a data.
    """
    fotos = [
        _rotulo_do_campo(campo, indicadores)
        for nome in indicadores
        for campo, especificacao in catalogo.INDICADORES[nome]["campos"].items()
        if _desempacotar_campo(especificacao)[2].get("foto_por")
    ]

    if not fotos or not periodo:
        return None

    hoje = date.today()

    if "dia" in periodo:
        fim = min(_inicio_e_fim(periodo["dia"])[1], hoje)
        return fotos, f"de hoje, {hoje:%d/%m/%Y}" if fim == hoje else f"em {fim:%d/%m/%Y}"

    if "ano" not in periodo:
        return None

    ano = max(int(valor) for valor in _como_lista(periodo["ano"]))
    mes = max((int(valor) for valor in _como_lista(periodo.get("mes", []))), default=12)
    ano, mes = min((ano, mes), (hoje.year, hoje.month))

    if {"mes", "ano"} & set(agrupar_por):
        quando = "no último dia de cada mês/ano da lista (no mês atual, hoje)"
    elif (ano, mes) == (hoje.year, hoje.month):
        quando = f"de hoje, {hoje:%d/%m/%Y}"
    else:
        quando = f"em {date(ano, mes, calendar.monthrange(ano, mes)[1]):%d/%m/%Y}"

    return fotos, quando


def _tabela_da_tela(
    resposta: dict, consulta: dict, indicador_def: dict, lados: tuple | None
) -> None:
    """As linhas da tabela, só com as colunas que a pergunta usou."""
    indicadores = [consulta["indicador"], *(consulta.get("cruzar_com") or [])]
    comparar_com = consulta.get("comparar_com")

    # Comparação entre itens sempre tem tabela (o campo principal).
    colunas = consulta.get("colunas") or (
        [indicador_def["campo_principal"]]
        if lados and indicador_def.get("campo_principal") else None
    )
    # Colunas escolhidas pelo sistema: a comparação só pro 1º campo.
    comparar = None
    rotulos = None
    pela_resposta = None

    if not colunas:
        colunas = _colunas_usadas_na_pergunta(consulta, indicador_def)
        comparar = colunas[:1] if colunas else None

        # Cruzamento: o principal de um indicador sem "colunas_no_cruzamento"
        # é só o padrão — a tela o troca pelos números que a resposta cita
        # (ex: "frequência" em vez de "clientes ativos").
        if colunas and consulta.get("cruzar_com") and not comparar_com and not lados:
            pela_resposta = {
                "opcionais": [
                    catalogo.INDICADORES[nome].get("campo_principal")
                    for nome in indicadores
                    if not catalogo.INDICADORES[nome].get("colunas_no_cruzamento")
                    and catalogo.INDICADORES[nome].get("campo_principal")
                    not in _campos_da_ordem_e_dos_filtros(consulta)
                ],
                "extras": [c for c in _campos_da_consulta(indicadores) if c not in colunas],
            }

        if colunas and comparar_com:
            colunas, rotulos = _colunas_da_comparacao_de_periodos(
                colunas, indicadores,
                _periodo_curto(_filtros_efetivos(indicador_def, consulta)),
                _periodo_curto(_filtros_efetivos(indicador_def, _do_periodo_comparado(consulta))),
            )
            comparar = []

    # Participação: o campo dela e o % logo depois.
    if resposta.get("participacao_sobre"):
        colunas = list(dict.fromkeys([*(colunas or [resposta["participacao_sobre"]["campo"]]), "participacao"]))

    if not colunas:
        return

    # Contagem do próprio item agrupado (ex: "clientes em risco" numa lista
    # de clientes) é 1 em toda linha: a situação já diz isso.
    agrupar_por = consulta.get("agrupar_por") or []
    colunas = [
        coluna for coluna in colunas
        if not any(
            (especificacao := catalogo.INDICADORES[nome]["campos"].get(coluna))
            and _desempacotar_campo(especificacao)[2].get("conta") in agrupar_por
            for nome in indicadores
        )
    ]

    # Lista sem outra coluna (ex: "quais clientes estão em risco"): o campo
    # pelo qual a lista vem ordenada (dias sem comprar).
    lista = indicador_def.get("lista_de_itens") or {}

    if not colunas and lista.get("ordem") and agrupar_por == [lista["dimensao"]]:
        colunas = [lista["ordem"][0]]

    if lados:
        lado_a, lado_b = lados
        rotulos = {}

        for coluna in colunas:
            rotulos[coluna] = lado_a
            rotulos[f"{coluna}_anterior"] = lado_b
            rotulos[f"diferenca_{coluna}"] = f"Diferença ({lado_a} − {lado_b})"
            rotulos[f"percentual_{coluna}"] = f"Diferença % ({lado_a} vs {lado_b})"

    if pela_resposta:
        pela_resposta["opcionais"] = [c for c in pela_resposta["opcionais"] if c in colunas]

    resposta["tabela"] = _linhas_da_tabela(
        resposta["resultados"], colunas, rotulos, comparar, pela_resposta
    )

    # Tabela só de campos "foto" (ex: lista de clientes em risco): a legenda
    # é o dia da situação, não o ano.
    foto = _momento_da_foto(indicadores, agrupar_por, resposta.get("periodo_consultado"))
    so_fotos = all(
        _desempacotar_campo(catalogo.INDICADORES[nome]["campos"][coluna])[2].get("foto_por")
        for coluna in colunas
        for nome in indicadores
        if coluna in catalogo.INDICADORES[nome]["campos"]
    )

    if foto and so_fotos and "de cada mês" not in foto[1]:
        for linha in resposta["tabela"]:
            linha["_legenda"] = f"Situação {foto[1]}"

    # Período em dias (ex: "ontem", "semana passada"): a legenda é o dia ou
    # as datas, não o ano.
    dia = _filtros_efetivos(indicador_def, consulta).get("dia")

    if dia and "dia" not in (consulta.get("agrupar_por") or []) and not lados:
        inicio, fim = _inicio_e_fim(dia)
        legenda = (
            f"Dia: {inicio:%d/%m/%Y}" if inicio == fim
            else f"Período: {inicio:%d/%m/%Y} a {fim:%d/%m/%Y}"
        )

        for linha in resposta["tabela"]:
            linha.setdefault("_legenda", legenda)

    # Sem período, num indicador que descreve o dele (ex: a inadimplência):
    # a legenda é essa descrição, não um ano achado no texto da resposta.
    sem_periodo = _descricao_sem_periodo(indicador_def)

    if (resposta.get("periodo_consultado") or {}).get("descricao") == sem_periodo and (
        (indicador_def.get("periodo_dos_campos") or {}).get("sem_periodo")
    ):
        for linha in resposta["tabela"]:
            linha.setdefault("_legenda", sem_periodo[0].upper() + sem_periodo[1:])


_DIMENSOES_DO_PERIODO = ("ano", "mes", "dia")


def _participacao(resposta: dict, consulta: dict) -> None:
    """
    Cada item ÷ o total do recorte, em % ("participacao"): o recorte é a
    mesma consulta só com o período e os filtros das dimensões de
    "dentro_de" (ex: ["filial"] = o total de Timon; [] = a empresa toda).
    Agrupado por mês/ano/dia, cada linha ÷ o total do SEU mês/ano/dia.
    """
    campo = _campo_da_participacao(consulta)
    dentro_de = consulta["participacao"].get("dentro_de") or []
    filtros = consulta.get("filtros") or {}
    tempo = [dimensao for dimensao in consulta.get("agrupar_por") or [] if dimensao in _DIMENSOES_DO_PERIODO]
    total = executar_consulta({
        "indicador": consulta["indicador"],
        "periodo": consulta.get("periodo"),
        "periodo_personalizado": consulta.get("periodo_personalizado"),
        "filtros": {
            dimensao: valores for dimensao, valores in filtros.items()
            if dimensao in _DIMENSOES_DO_PERIODO or dimensao in dentro_de
        },
        "agrupar_por": tempo,
    })
    totais = {tuple(linha.get(d) for d in tempo): linha.get(campo) for linha in total["resultados"]}

    if not any(totais.values()):
        return

    for linha in resposta["resultados"]:
        valor_total = totais.get(tuple(linha.get(d) for d in tempo))

        if linha.get(campo) is not None and valor_total:
            linha["participacao"] = round(linha[campo] / valor_total * 100, 2)

            if tempo:
                linha["total_da_participacao"] = valor_total

    valor_total = None if tempo else totais[()]

    total_de = " e ".join(
        ", ".join(map(str, filtros[dimensao])) for dimensao in dentro_de if dimensao in filtros
    )
    total_de = f"de {total_de}" if total_de else "da empresa toda"
    rotulo = _rotulo_do_campo(campo, [consulta["indicador"]]).lower()
    resposta["participacao_sobre"] = {
        "campo": campo,
        "total": valor_total,
        "total_de": total_de,
        "como_ler": (
            f"'participacao' de cada item = {campo} dele ÷ o total {total_de} "
            "(mesmo período; agrupado por mês/ano, o total daquele mês/ano, em "
            f"'total_da_participacao'), em %. Ex: \"1,30% do {rotulo} {total_de} "
            "(R$ 1.451.888,37 de R$ 112.114.507,37)\"."
        ),
    }


def _descricao_sem_periodo(indicador_def: dict) -> str:
    """Campo com período próprio (ex: a inadimplência oficial) diz o dele."""
    sem_periodo = (indicador_def.get("periodo_dos_campos") or {}).get("sem_periodo")
    return sem_periodo() if sem_periodo else "todo o histórico disponível (sem filtro de período)"


def executar_consulta(consulta: dict) -> dict:
    """
    Ponto único de entrada do motor. `consulta`:
    - indicador (obrigatório): nome no catálogo;
    - periodo / periodo_personalizado: um de catalogo.PERIODOS_VALIDOS, ou
      {"meses", "anos"} / {"data_inicial", "data_final"};
    - filtros: {dimensão: valor ou lista}; agrupar_por: lista de dimensões;
    - comparar_com (+ comparar_com_personalizado): outro período — cada
      campo ganha _anterior/diferenca_/percentual_;
    - comparar_filtros: item x item da mesma dimensão (ex: filial A x B),
      que não pode estar em agrupar_por;
    - cruzar_com: outros indicadores, com os mesmos filtros e período;
    - filtros_calculados: [{"campo", "operador", "valor"}] sobre o resultado
      já somado (ex: só quem bateu a meta);
    - ordenar_por: {"campo", "ordem": "desc"|"asc", "limite": N} — e, com
      "por" (uma dimensão de agrupar_por) e "limite_grupos": M, os M grupos
      de maior total com N linhas dentro de cada;
    - colunas: o que a TABELA mostra (a IA recebe tudo).
    """
    consulta = _preparar_consulta(consulta)
    indicador_def = catalogo.INDICADORES[consulta["indicador"]]
    pedida = consulta

    consulta, contexto = _ajustar_periodo(consulta, indicador_def)
    resultado, extras, lados = _consultar(consulta, indicador_def)
    resultado = _sem_campos_fora_do_recorte(resultado, consulta)

    if extras.get("total"):
        extras["total"] = _sem_campos_fora_do_recorte([extras["total"]], consulta)[0]

    resultado, fora_da_lista = _separar_sem_valor(
        resultado,
        [catalogo.INDICADORES[nome] for nome in [consulta["indicador"], *(consulta.get("cruzar_com") or [])]],
        consulta.get("ordenar_por"),
        consulta.get("agrupar_por"),
    )
    lista = _lista_de_itens(indicador_def, consulta, resultado)

    if lista and lista.get("ordem") and not consulta.get("ordenar_por"):
        # Só reordena: quem não tem valor no campo vai pro fim, sem sair.
        campo, ordem = lista["ordem"]
        com_valor = [linha for linha in resultado if linha.get(campo) is not None]
        resultado = _aplicar_ordenacao(com_valor, {"campo": campo, "ordem": ordem}) + [
            linha for linha in resultado if linha.get(campo) is None
        ]

    resultado_antes_do_limite = resultado
    resultado, totais_por_grupo = _ordenar(resultado, consulta.get("ordenar_por"), extras)

    resposta = {
        "encontrado": bool(resultado),
        "indicador": consulta["indicador"],
        "cruzado_com": consulta.get("cruzar_com") or None,
        "filtros_aplicados": consulta.get("filtros"),
        # O critério ("dias sem comprar > 730") vai junto: quem escreve diz
        # "há mais de 730 dias" e a conferência de números aceita o 730.
        "filtros_sobre_a_metrica": consulta.get("filtros_calculados") or None,
        "periodo_consultado": contexto["periodo_consultado"] or {
            "descricao": _descricao_sem_periodo(indicador_def)
        },
        "agrupar_por": consulta.get("agrupar_por") or None,
        "resultados": resultado,
    }

    if totais_por_grupo is not None:
        resposta["totais_por_grupo"] = totais_por_grupo

    if fora_da_lista is not None:
        resposta["fora_da_lista_de_menor"] = fora_da_lista

    _avisos_para_a_ia(resposta, consulta, indicador_def, contexto, extras, resultado_antes_do_limite)

    if lista:
        _avisos_da_lista(resposta, lista, consulta, resultado_antes_do_limite)

    if consulta.get("comparar_com"):
        resposta["periodo_comparado"] = _descrever_periodo(
            _filtros_efetivos(indicador_def, _do_periodo_comparado(consulta))
        )

    if lados:
        lado_a, lado_b = lados
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

    if pedida.get("participacao") is not None:
        _participacao(resposta, pedida)

    _tabela_da_tela(resposta, consulta, indicador_def, lados)

    return resposta
