"""
Ferramentas do módulo de NPS.

Este arquivo faz a ponte entre os nomes conhecidos pela IA
e as funções reais de consulta existentes em queries.py.
"""

from src.queries import (
    comparar_nps_periodos,
    obter_nps_por_filial,
    obter_nps_por_periodo,
    obter_resumo_nps,
)

def executar_nps_geral(argumentos: dict) -> dict:
    """
    Consulta o NPS geral da empresa.
    """

    return obter_resumo_nps()


def executar_nps_por_filial(argumentos: dict) -> dict:
    """
    Consulta o NPS de uma filial específica.
    """

    filial_procurada = argumentos.get("filial")

    if not filial_procurada:
        raise ValueError(
            "O argumento 'filial' é obrigatório."
        )

    filiais = obter_nps_por_filial()

    nome_procurado = filial_procurada.strip().casefold()

    for filial in filiais:
        nome_filial = filial["filial"]

        if nome_filial.casefold() == nome_procurado:
            return filial

    raise ValueError(
        f"A filial '{filial_procurada}' não foi encontrada."
    )

def executar_nps_por_periodo(argumentos: dict) -> dict:
    """
    Consulta o NPS dentro de um intervalo de datas.
    """

    data_inicial = argumentos.get("data_inicial")
    data_final = argumentos.get("data_final")

    if not data_inicial or not data_final:
        raise ValueError(
            "Os argumentos 'data_inicial' e 'data_final' "
            "são obrigatórios."
        )

    return obter_nps_por_periodo(
        data_inicial,
        data_final,
    )

def executar_comparacao_nps(argumentos: dict) -> dict:
    """
    Compara o NPS entre dois períodos.
    """

    data_inicial_atual = argumentos.get(
        "data_inicial_atual"
    )
    data_final_atual = argumentos.get(
        "data_final_atual"
    )
    data_inicial_anterior = argumentos.get(
        "data_inicial_anterior"
    )
    data_final_anterior = argumentos.get(
        "data_final_anterior"
    )

    argumentos_faltantes = []

    if not data_inicial_atual:
        argumentos_faltantes.append(
            "data_inicial_atual"
        )

    if not data_final_atual:
        argumentos_faltantes.append(
            "data_final_atual"
        )

    if not data_inicial_anterior:
        argumentos_faltantes.append(
            "data_inicial_anterior"
        )

    if not data_final_anterior:
        argumentos_faltantes.append(
            "data_final_anterior"
        )

    if argumentos_faltantes:
        raise ValueError(
            "Argumentos obrigatórios ausentes: "
            + ", ".join(argumentos_faltantes)
        )

    return comparar_nps_periodos(
        data_inicial_atual,
        data_final_atual,
        data_inicial_anterior,
        data_final_anterior,
    )