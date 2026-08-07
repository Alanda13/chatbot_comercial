"""
Ferramentas do módulo de NPS.

Este arquivo faz a ponte entre os nomes conhecidos pela IA
e as funções reais de consulta existentes em queries.py.
"""
import difflib

from src.queries import (
    comparar_nps_entre_periodos,
    obter_nps_filial_periodo,
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

    A busca aceita:
    - nomes completos;
    - nomes parciais;
    - pequenas diferenças de escrita.

    Exemplos:
    - "Timon" encontra "FERRONORTE TIMON";
    - "Campo Sales" encontra "FERRONORTE CAMPOS SALES".
    """

    filial_procurada = argumentos.get("filial")

    if not filial_procurada:
        raise ValueError(
            "O argumento 'filial' é obrigatório."
        )

    filiais = obter_nps_por_filial()

    nome_procurado = filial_procurada.strip().casefold()

    # Remove palavras que podem aparecer ou não no nome informado.
    nome_procurado_simplificado = (
        nome_procurado
        .replace("ferronorte", "")
        .replace("ferroleste", "")
        .replace("filial", "")
        .replace("loja", "")
        .strip()
    )
    correspondencias = []

    for dados_filial in filiais:
        nome_filial = dados_filial["filial"].strip()
        nome_filial_normalizado = nome_filial.casefold()

        nome_filial_simplificado = (
            nome_filial_normalizado
            .replace("ferronorte", "")
            .replace("ferroleste", "")
            .replace("filial", "")
            .replace("loja", "")
            .strip()
        )

        # Primeiro tenta encontrar pelo nome completo ou parcial.
        if (
            nome_procurado in nome_filial_normalizado
            or nome_procurado_simplificado
            in nome_filial_simplificado
        ):
            return dados_filial

        # Se não encontrar, calcula a semelhança entre os nomes.
        similaridade = difflib.SequenceMatcher(
            None,
            nome_procurado_simplificado,
            nome_filial_simplificado,
        ).ratio()

        correspondencias.append(
            (
                similaridade,
                dados_filial,
            )
        )

    # Ordena da filial mais parecida para a menos parecida.
    correspondencias.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    melhor_similaridade, melhor_filial = correspondencias[0]

    # Aceita a filial quando a semelhança for suficiente.
    if melhor_similaridade >= 0.75:
        return melhor_filial

    raise ValueError(
        f"A filial '{filial_procurada}' não foi encontrada."
    )

## mudanças na função de executar nps por periodo
def executar_nps_por_periodo(argumentos: dict) -> dict:
    """
    Consulta os indicadores de NPS dentro de um intervalo de datas.
    """

    data_inicial = argumentos.get("data_inicial")
    data_final = argumentos.get("data_final")

    indicador = argumentos.get(
        "indicador",
        "resumo",
    )

    if not data_inicial or not data_final:
        raise ValueError(
            "Os argumentos 'data_inicial' e 'data_final' "
            "são obrigatórios."
        )

    resultado = obter_nps_por_periodo(
        data_inicial,
        data_final,
    )

    resultado["indicador"] = indicador

    return resultado

## função que vai fazer a compração entre os nps
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

    return comparar_nps_entre_periodos(
        data_inicial_atual,
        data_final_atual,
        data_inicial_anterior,
        data_final_anterior,
    )

def executar_nps_filial_periodo(argumentos: dict) -> dict:
    """
    Consulta os indicadores de NPS de uma filial
    dentro de um período informado.
    """

    filial_procurada = argumentos.get("filial")
    data_inicial = argumentos.get("data_inicial")
    data_final = argumentos.get("data_final")

    indicador = argumentos.get(
        "indicador",
        "resumo",
    )

    argumentos_faltantes = []

    if not filial_procurada:
        argumentos_faltantes.append("filial")

    if not data_inicial:
        argumentos_faltantes.append("data_inicial")

    if not data_final:
        argumentos_faltantes.append("data_final")

    if argumentos_faltantes:
        raise ValueError(
            "Argumentos obrigatórios ausentes: "
            + ", ".join(argumentos_faltantes)
        )

    filiais = obter_nps_por_filial()

    nome_procurado = filial_procurada.strip().casefold()

    nome_procurado_simplificado = (
        nome_procurado
        .replace("ferronorte", "")
        .replace("ferroleste", "")
        .replace("filial", "")
        .replace("loja", "")
        .strip()
    )

    correspondencias = []

    for dados_filial in filiais:
        nome_filial = dados_filial["filial"].strip()
        nome_filial_normalizado = nome_filial.casefold()

        nome_filial_simplificado = (
            nome_filial_normalizado
            .replace("ferronorte", "")
            .replace("ferroleste", "")
            .replace("filial", "")
            .replace("loja", "")
            .strip()
        )

        if (
            nome_procurado in nome_filial_normalizado
            or nome_procurado_simplificado
            in nome_filial_simplificado
        ):
            resultado = obter_nps_filial_periodo(
                nome_filial,
                data_inicial,
                data_final,
            )

            resultado["indicador"] = indicador

            return resultado

        similaridade = difflib.SequenceMatcher(
            None,
            nome_procurado_simplificado,
            nome_filial_simplificado,
        ).ratio()

        correspondencias.append(
            (
                similaridade,
                nome_filial,
            )
        )

    correspondencias.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    melhor_similaridade, melhor_nome_filial = correspondencias[0]

    if melhor_similaridade >= 0.75:
        resultado = obter_nps_filial_periodo(
            melhor_nome_filial,
            data_inicial,
            data_final,
        )

        resultado["indicador"] = indicador

        return resultado

    raise ValueError(
        f"A filial '{filial_procurada}' não foi encontrada."
    )

