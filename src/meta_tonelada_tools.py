"""
Ferramentas do indicador de Meta de Tonelada.

Este arquivo faz a ponte entre os nomes informados pela IA e a
consulta de meta de tonelada.
"""
from src.meta_tonelada_queries import consultar_meta_tonelada
from src.meta_tonelada_data import (
    resolver_nome_filial_tonelada,
    resolver_nomes_rca_tonelada,
)


def executar_consultar_meta_tonelada(argumentos: dict) -> dict:
    """
    Executa uma consulta genérica de meta de tonelada.

    Pode receber:
    - filiais;
    - rcas;
    - meses;
    - anos;
    - agrupar_por.
    """

    filiais = argumentos.get("filiais")
    rcas = argumentos.get("rcas")
    meses = argumentos.get("meses")
    anos = argumentos.get("anos")
    agrupar_por = argumentos.get("agrupar_por")

    filiais_resolvidas = None

    if filiais:
        filiais_resolvidas = []

        for filial in filiais:
            nome_resolvido = resolver_nome_filial_tonelada(filial)

            if nome_resolvido not in filiais_resolvidas:
                filiais_resolvidas.append(nome_resolvido)

    rcas_resolvidos = None

    if rcas:
        rcas_resolvidos = []

        for rca in rcas:
            for nome in resolver_nomes_rca_tonelada(
                rca,
                filiais=filiais_resolvidas,
            ):
                if nome not in rcas_resolvidos:
                    rcas_resolvidos.append(nome)

    return consultar_meta_tonelada(
        filiais=filiais_resolvidas,
        rcas=rcas_resolvidos,
        meses=meses,
        anos=anos,
        agrupar_por=agrupar_por,
    )
