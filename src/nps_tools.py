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
    - um período;
    - vários períodos.
    """

    filial = argumentos.get("filial")
    periodos = argumentos.get("periodos")

    # Se o usuário não informou uma filial,
    # consulta os indicadores da empresa inteira.
    if not filial:
        return consultar_indicadores_nps(
            filial=None,
            periodos=periodos,
        )

    # Busca as filiais existentes no banco.
    filiais = obter_nps_por_filial()

    # Normaliza o nome informado pelo usuário.
    # Exemplo: "Filial de Santa Inês" -> "santa ines"
    nome_procurado = normalizar_nome_filial(
        filial
    )

    correspondencias = []

    for dados_filial in filiais:
        nome_filial = dados_filial["filial"].strip()

        # Normaliza também o nome que veio do banco.
        # Exemplo: "FERRONORTE TIMON" -> "timon"
        nome_filial_normalizado = normalizar_nome_filial(
            nome_filial
        )

        # Primeiro tenta encontrar diretamente.
        if (
            nome_procurado in nome_filial_normalizado
            or nome_filial_normalizado in nome_procurado
        ):
            return consultar_indicadores_nps(
                filial=nome_filial,
                periodos=periodos,
            )

        # Se não encontrou diretamente, calcula
        # o quanto os dois nomes são parecidos.
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

    # Coloca a filial mais parecida em primeiro lugar.
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
    # Se o nome for suficientemente parecido,
    # aceita a filial encontrada.
    if melhor_similaridade >= 0.75:
        return consultar_indicadores_nps(
            filial=melhor_nome_filial,
            periodos=periodos,
        )

    raise ValueError(
        f"A filial '{filial}' não foi encontrada."
    )
