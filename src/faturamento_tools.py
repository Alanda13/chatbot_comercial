"""
Ferramentas do módulo de faturamento.

Este arquivo faz a ponte entre os nomes informados pela IA
e as consultas de faturamento.
"""

import difflib
import unicodedata

from src.faturamento_queries import (
    consultar_indicadores_faturamento,
    listar_filiais_faturamento,
)


def normalizar_nome_filial(nome: str) -> str:
    """
    Normaliza o nome da filial para facilitar
    buscas e comparações aproximadas.
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
        nome = nome.replace(
            palavra,
            " ",
        )

    nome = " ".join(
        nome.split()
    )

    return nome


def resolver_nome_filial(nome_informado: str) -> str:
    """
    Encontra o nome correto da filial na base de faturamento.
    """

    filiais = listar_filiais_faturamento()

    nome_procurado = normalizar_nome_filial(
        nome_informado
    )

    correspondencias = []

    for filial in filiais:
        nome_normalizado = normalizar_nome_filial(
            filial
        )

        # Primeiro tenta encontrar diretamente.
        if (
            nome_procurado in nome_normalizado
            or nome_normalizado in nome_procurado
        ):
            return filial

        # Se não encontrou diretamente,
        # calcula a similaridade entre os nomes.
        similaridade = difflib.SequenceMatcher(
            None,
            nome_procurado,
            nome_normalizado,
        ).ratio()

        correspondencias.append(
            (
                similaridade,
                filial,
            )
        )

    if not correspondencias:
        raise ValueError(
            "Nenhuma filial foi encontrada "
            "na base de faturamento."
        )

    correspondencias.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    melhor_similaridade, melhor_filial = (
        correspondencias[0]
    )

    # Aceita pequenos erros de digitação.
    if melhor_similaridade >= 0.75:
        return melhor_filial

    raise ValueError(
        f"A filial '{nome_informado}' não foi encontrada."
    )


def executar_consulta_indicadores_faturamento(
    argumentos: dict,
) -> dict:
    """
    Executa uma consulta genérica de faturamento.

    Pode receber:
    - filiais;
    - rcas;
    - meses;
    - anos.
    """

    filiais = argumentos.get("filiais")
    rcas = argumentos.get("rcas")
    meses = argumentos.get("meses")
    anos = argumentos.get("anos")
    agrupar_por = argumentos.get("agrupar_por")

    filiais_resolvidas = None

    # Se foram informadas filiais,
    # resolve cada nome para o nome existente na base.
    if filiais:
        filiais_resolvidas = []

        for filial in filiais:
            nome_resolvido = resolver_nome_filial(
                filial
            )

            # Evita repetir a mesma filial.
            if nome_resolvido not in filiais_resolvidas:
                filiais_resolvidas.append(
                    nome_resolvido
                )

    return consultar_indicadores_faturamento(
        filiais=filiais_resolvidas,
        rcas=rcas,
        meses=meses,
        anos=anos,
        agrupar_por=agrupar_por,
    )