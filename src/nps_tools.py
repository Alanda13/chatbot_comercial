"""
Ferramentas do módulo de NPS.

Este arquivo faz a ponte entre os nomes conhecidos pela IA
e as funções reais de consulta existentes em queries.py.
"""
import difflib
import unicodedata

from src.queries import (
    consultar_indicadores_nps,
    obter_nps_por_filial,
)

def normalizar_nome_filial(nome: str) -> str:
    """
    Normaliza o nome de uma filial para facilitar
    comparações e buscas aproximadas.
    """

    nome = nome.strip().casefold()
    nome = unicodedata.normalize(
        "NFKD",
        nome,
    )
    nome = "".join(
        caractere
        for caractere in nome
        if not unicodedata.combining(caractere)
    )
    palavras_remover = [
        "ferronorte",
        "ferroleste",
        "filial",
        "loja",
        "unidade",
        "de",
        "da",
        "do",
    ]

    for palavra in palavras_remover:
        nome = nome.replace(palavra, " ")

    nome = " ".join(nome.split())

    return nome

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

    # Se nenhuma filial foi informada,
    # consulta a empresa inteira.
    if not filiais_solicitadas:
        return consultar_indicadores_nps(
            filiais=None,
            periodos=periodos,
        )

    # Garante que sempre trabalharemos com uma lista.
    if isinstance(filiais_solicitadas, str):
        filiais_solicitadas = [filiais_solicitadas]

    filiais_banco = obter_nps_por_filial()
    filiais_encontradas = []

    for filial_solicitada in filiais_solicitadas:
        nome_procurado = normalizar_nome_filial(
            filial_solicitada
        )

        correspondencias = []
        filial_encontrada = None

        for dados_filial in filiais_banco:
            nome_filial = dados_filial["filial"].strip()

            nome_filial_normalizado = normalizar_nome_filial(
                nome_filial
            )

            if (
                nome_procurado in nome_filial_normalizado
                or nome_filial_normalizado in nome_procurado
            ):
                filial_encontrada = nome_filial
                break

            similaridade = difflib.SequenceMatcher(
                None,
                nome_procurado,
                nome_filial_normalizado,
            ).ratio()

            correspondencias.append(
                (
                    similaridade,
                    nome_filial,
                )
            )

        if filial_encontrada is None:
            correspondencias.sort(
                key=lambda item: item[0],
                reverse=True,
            )

            if not correspondencias:
                raise ValueError(
                    "Nenhuma filial foi encontrada no banco."
                )

            melhor_similaridade, melhor_nome_filial = (
                correspondencias[0]
            )

            if melhor_similaridade >= 0.75:
                filial_encontrada = melhor_nome_filial

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
    )