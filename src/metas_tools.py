"""
Ferramentas do módulo de Metas.

Este arquivo faz a ponte entre os nomes informados pela IA
e a consulta de metas.
"""
from src.metas_queries import consultar_metas
from src.metas_data import resolver_codigos_supervisor
from src.faturamento_diario_data import resolver_codigos_rca
from src.faturamento_tools import resolver_nome_filial


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

    filiais = argumentos.get("filiais")
    rcas = argumentos.get("rcas")
    supervisores = argumentos.get("supervisores")
    meses = argumentos.get("meses")
    anos = argumentos.get("anos")
    agrupar_por = argumentos.get("agrupar_por")

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

    return consultar_metas(
        filiais=filiais_resolvidas,
        rcas=rcas_resolvidos,
        supervisores=supervisores_resolvidos,
        meses=meses,
        anos=anos,
        agrupar_por=agrupar_por,
    )
