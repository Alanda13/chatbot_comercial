"""
Ferramentas do módulo de NPS.

Este arquivo faz a ponte entre os nomes conhecidos pela IA
e as funções reais de consulta existentes em queries.py.
"""
from src.queries import (
    consultar_indicadores_nps,
    obter_evolucao_nps_por_filial,
    obter_nps_por_filial,
)
from src.filial_utils import (
    encontrar_filial_mais_proxima,
    normalizar_nome_filial,
)


def _resolver_filiais(filiais_solicitadas) -> list[str] | None:
    """
    Resolve os nomes de filiais informados pela IA para os nomes
    reais cadastrados na base de NPS.
    """
    if not filiais_solicitadas:
        return None

    if isinstance(filiais_solicitadas, str):
        filiais_solicitadas = [filiais_solicitadas]

    nomes_disponiveis = [
        dados_filial["filial"].strip()
        for dados_filial in obter_nps_por_filial()
    ]

    if not nomes_disponiveis:
        raise ValueError("Nenhuma filial foi encontrada no banco.")

    filiais_encontradas = []

    for filial_solicitada in filiais_solicitadas:
        nome_procurado = normalizar_nome_filial(
            filial_solicitada
        )

        filial_encontrada = encontrar_filial_mais_proxima(
            nome_procurado,
            nomes_disponiveis,
        )

        if filial_encontrada is None:
            raise ValueError(
                f"A filial '{filial_solicitada}' "
                "não foi encontrada."
            )

        filiais_encontradas.append(
            filial_encontrada
        )

    return filiais_encontradas


def executar_consulta_indicadores_nps(argumentos: dict) -> dict:
    """
    Executa consultas genéricas de indicadores de NPS.

    Pode consultar:
    - empresa inteira;
    - uma filial;
    - várias filiais;
    - um período;
    - vários períodos.
    """

    filiais_solicitadas = argumentos.get("filiais")
    periodos = argumentos.get("periodos")
    agrupar_por_filial = bool(
        argumentos.get("agrupar_por_filial")
    )
    agrupar_por_ano = bool(
        argumentos.get("agrupar_por_ano")
    )
    agrupar_por_mes = bool(
        argumentos.get("agrupar_por_mes")
    )
    ano = argumentos.get("ano")

    # Se nenhuma filial foi informada,
    # consulta a empresa inteira (ou todas as filiais
    # agrupadas, se agrupar_por_filial for True).
    if not filiais_solicitadas:
        return consultar_indicadores_nps(
            filiais=None,
            periodos=periodos,
            agrupar_por_filial=agrupar_por_filial,
            agrupar_por_ano=agrupar_por_ano,
            agrupar_por_mes=agrupar_por_mes,
            ano=ano,
        )

    # Garante que sempre trabalharemos com uma lista.
    if isinstance(filiais_solicitadas, str):
        filiais_solicitadas = [filiais_solicitadas]

    nomes_disponiveis = [
        dados_filial["filial"].strip()
        for dados_filial in obter_nps_por_filial()
    ]

    if not nomes_disponiveis:
        raise ValueError("Nenhuma filial foi encontrada no banco.")

    filiais_encontradas = []

    for filial_solicitada in filiais_solicitadas:
        nome_procurado = normalizar_nome_filial(
            filial_solicitada
        )

        filial_encontrada = encontrar_filial_mais_proxima(
            nome_procurado,
            nomes_disponiveis,
        )

        if filial_encontrada is None:
            raise ValueError(
                f"A filial '{filial_solicitada}' "
                "não foi encontrada."
            )

        filiais_encontradas.append(
            filial_encontrada
        )

    return consultar_indicadores_nps(
        filiais=filiais_encontradas,
        periodos=periodos,
        agrupar_por_ano=agrupar_por_ano,
        agrupar_por_mes=agrupar_por_mes,
        ano=ano,
    )


def executar_consultar_evolucao_nps(argumentos: dict) -> dict:
    """
    Executa a consulta de evolução de NPS entre dois anos, por
    filial — já ordenado da maior evolução (positiva) pra maior
    queda, calculado em Python (não pela IA).
    """
    ano_inicial = argumentos.get("ano_inicial")
    ano_final = argumentos.get("ano_final")
    filiais_resolvidas = _resolver_filiais(
        argumentos.get("filiais")
    )

    resultados = obter_evolucao_nps_por_filial(
        ano_inicial=ano_inicial,
        ano_final=ano_final,
        filiais=filiais_resolvidas,
    )

    return {
        "encontrado": bool(resultados),
        "ano_inicial": ano_inicial,
        "ano_final": ano_final,
        "resultados": resultados,
    }