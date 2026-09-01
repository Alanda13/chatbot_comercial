"""
Consultas de indicadores de Metas.

Usa a mesma base da rotina 8280 (Faturamento por RCA/Filial/Mês/Ano),
que já traz VALOR_META e PERC_META por linha.
"""
import calendar
from datetime import date, timedelta

import pandas as pd

from src.faturamento_data import carregar_faturamento_8280
from src.faturamento_diario_data import construir_mapa_rca_nome
from src.metas_data import construir_lista_supervisores


def _calcular_dias_uteis_restantes(ano: int, mes: int) -> int | None:
    """
    Conta os dias úteis (segunda a sexta) restantes no mês, a partir
    de hoje (inclusive), sem considerar feriados.

    Só faz sentido para o mês/ano atual — para qualquer outro
    período, retorna None (não há "necessidade diária" de um mês que
    já passou ou que ainda nem começou).
    """
    hoje = date.today()

    if (ano, mes) != (hoje.year, hoje.month):
        return None

    ultimo_dia = calendar.monthrange(ano, mes)[1]
    fim_do_mes = date(ano, mes, ultimo_dia)

    dias_uteis = 0
    dia_atual = hoje

    while dia_atual <= fim_do_mes:
        if dia_atual.weekday() < 5:
            dias_uteis += 1
        dia_atual += timedelta(days=1)

    return dias_uteis


def consultar_metas(
    filiais: list[str] | None = None,
    rcas: list[int] | None = None,
    supervisores: list[int] | None = None,
    meses: list[int] | None = None,
    anos: list[int] | None = None,
    agrupar_por: list[str] | None = None,
) -> dict:
    """
    Consulta indicadores de metas da rotina 8280.

    Os filtros são opcionais e podem ser combinados:
    - filiais;
    - RCAs;
    - supervisores;
    - meses;
    - anos.

    Também pode agrupar os resultados por:
    - filial;
    - RCA;
    - supervisor;
    - mês;
    - ano.
    """
    dados = carregar_faturamento_8280()

    if filiais:
        dados = dados[dados["FILIAL"].isin(filiais)]

    if rcas:
        dados = dados[dados["COD_RCA"].isin(rcas)]

    if supervisores:
        dados = dados[dados["COD_SUPERVISOR"].isin(supervisores)]

    if meses:
        dados = dados[dados["MES"].isin(meses)]

    if anos:
        dados = dados[dados["ANO"].isin(anos)]

    filtros_aplicados = {
        "filiais": filiais,
        "rcas": rcas,
        "supervisores": supervisores,
        "meses": meses,
        "anos": anos,
    }

    if dados.empty:
        return {
            "encontrado": False,
            "filtros_aplicados": filtros_aplicados,
            "mensagem": (
                "Nenhuma meta encontrada para os filtros informados."
            ),
        }

    if not agrupar_por:
        valor_meta = round(float(dados["VALOR_META"].sum()), 2)
        faturamento_realizado = round(float(dados["VENDA_LIQ"].sum()), 2)
        falta_para_meta = round(valor_meta - faturamento_realizado, 2)
        percentual_atingimento = (
            round(faturamento_realizado / valor_meta * 100, 2)
            if valor_meta
            else None
        )

        resultado = {
            "encontrado": True,
            "filtros_aplicados": filtros_aplicados,
            "valor_meta": valor_meta,
            "faturamento_realizado": faturamento_realizado,
            "falta_para_meta": falta_para_meta,
            "percentual_atingimento": percentual_atingimento,
        }

        if meses and anos and len(meses) == 1 and len(anos) == 1:
            dias_uteis_restantes = _calcular_dias_uteis_restantes(
                anos[0], meses[0]
            )

            if dias_uteis_restantes:
                resultado["necessidade_diaria"] = round(
                    falta_para_meta / dias_uteis_restantes, 2
                )

        return resultado

    mapa_agrupamentos = {
        "filial": "FILIAL",
        "rca": "COD_RCA",
        "supervisor": "COD_SUPERVISOR",
        "mes": "MES",
        "ano": "ANO",
    }

    colunas_agrupamento = []

    for agrupamento in agrupar_por:
        if agrupamento not in mapa_agrupamentos:
            raise ValueError(
                f"Agrupamento inválido: '{agrupamento}'."
            )

        colunas_agrupamento.append(
            mapa_agrupamentos[agrupamento]
        )

    mapa_rca_nome = {}

    if "rca" in agrupar_por:
        try:
            mapa_rca_nome = construir_mapa_rca_nome()
        except FileNotFoundError:
            mapa_rca_nome = {}

    mapa_supervisor_nome = {}

    if "supervisor" in agrupar_por:
        mapa_supervisor_nome = {
            supervisor["codigo"]: supervisor["nome"]
            for supervisor in construir_lista_supervisores()
        }

    agrupado = (
        dados
        .groupby(
            colunas_agrupamento,
            dropna=False,
        )
        .agg(
            valor_meta=("VALOR_META", "sum"),
            faturamento_realizado=("VENDA_LIQ", "sum"),
        )
        .reset_index()
    )

    resultados = []

    for _, linha in agrupado.iterrows():
        item = {}

        for agrupamento, coluna in zip(
            agrupar_por,
            colunas_agrupamento,
        ):
            valor = linha[coluna]

            if agrupamento in ["ano", "mes", "rca", "supervisor"]:
                valor = int(valor)
            elif pd.isna(valor):
                valor = "Não informado"
            else:
                valor = str(valor)

            item[agrupamento] = valor

            if agrupamento == "rca":
                item["rca_nome"] = mapa_rca_nome.get(valor)

            if agrupamento == "supervisor":
                item["supervisor_nome"] = mapa_supervisor_nome.get(valor)

        valor_meta_item = round(float(linha["valor_meta"]), 2)
        faturamento_item = round(
            float(linha["faturamento_realizado"]), 2
        )
        falta_item = round(valor_meta_item - faturamento_item, 2)
        percentual_item = (
            round(faturamento_item / valor_meta_item * 100, 2)
            if valor_meta_item
            else None
        )

        item["valor_meta"] = valor_meta_item
        item["faturamento_realizado"] = faturamento_item
        item["falta_para_meta"] = falta_item
        item["percentual_atingimento"] = percentual_item

        resultados.append(item)

    return {
        "encontrado": True,
        "filtros_aplicados": filtros_aplicados,
        "agrupar_por": agrupar_por,
        "resultados": resultados,
    }
