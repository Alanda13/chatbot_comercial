"""
Ferramentas do módulo de Metas.

Este arquivo faz a ponte entre os nomes informados pela IA
e a consulta de metas.
"""
from src.metas_queries import (
    consultar_metas,
    consultar_crescimento_abaixo_meta,
)
from src.metas_data import resolver_codigos_supervisor
from src.faturamento_diario_data import resolver_codigos_rca
from src.faturamento_tools import resolver_nome_filial


def _resolver_filtros(argumentos: dict) -> tuple:
    """
    Resolve filiais, rcas e supervisores informados pela IA para os
    valores reais usados na base (mesma lógica usada em
    executar_consultar_metas).
    """
    filiais = argumentos.get("filiais")
    rcas = argumentos.get("rcas")
    supervisores = argumentos.get("supervisores")

    filiais_resolvidas = None

    if filiais:
        filiais_resolvidas = []

        for filial in filiais:
            nome_resolvido = resolver_nome_filial(filial)

            if nome_resolvido not in filiais_resolvidas:
                filiais_resolvidas.append(nome_resolvido)

    rcas_resolvidos = None

    if rcas:
        rcas_resolvidos = []

        for rca in rcas:
            for codigo in resolver_codigos_rca(
                rca,
                filiais=filiais_resolvidas,
            ):
                if codigo not in rcas_resolvidos:
                    rcas_resolvidos.append(codigo)

    supervisores_resolvidos = None

    if supervisores:
        supervisores_resolvidos = []

        for supervisor in supervisores:
            for codigo in resolver_codigos_supervisor(
                supervisor,
                filiais=filiais_resolvidas,
            ):
                if codigo not in supervisores_resolvidos:
                    supervisores_resolvidos.append(codigo)

    return filiais_resolvidas, rcas_resolvidos, supervisores_resolvidos


def executar_consultar_metas(argumentos: dict) -> dict:
    """
    Executa uma consulta genérica de metas.

    Pode receber:
    - filiais;
    - rcas;
    - supervisores;
    - meses;
    - anos;
    - agrupar_por.
    """

    meses = argumentos.get("meses")
    anos = argumentos.get("anos")
    agrupar_por = argumentos.get("agrupar_por")

    filiais_resolvidas, rcas_resolvidos, supervisores_resolvidos = (
        _resolver_filtros(argumentos)
    )

    return consultar_metas(
        filiais=filiais_resolvidas,
        rcas=rcas_resolvidos,
        supervisores=supervisores_resolvidos,
        meses=meses,
        anos=anos,
        agrupar_por=agrupar_por,
    )


def executar_consultar_crescimento_abaixo_meta(argumentos: dict) -> dict:
    """
    Executa a consulta de filiais/RCAs/supervisores que cresceram em
    faturamento em relação ao ano anterior e ainda estão abaixo da
    meta no ano informado.

    Recebe:
    - ano (obrigatório);
    - filiais, rcas, supervisores (opcionais);
    - agrupar_por: "filial" (padrão), "rca" ou "supervisor".
    """
    ano = argumentos.get("ano")
    agrupar_por = argumentos.get("agrupar_por") or "filial"

    if isinstance(agrupar_por, list):
        agrupar_por = agrupar_por[0] if agrupar_por else "filial"

    filiais_resolvidas, rcas_resolvidos, supervisores_resolvidos = (
        _resolver_filtros(argumentos)
    )

    return consultar_crescimento_abaixo_meta(
        ano=ano,
        filiais=filiais_resolvidas,
        rcas=rcas_resolvidos,
        supervisores=supervisores_resolvidos,
        agrupar_por=agrupar_por,
    )
