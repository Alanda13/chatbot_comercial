"""
Utilitários compartilhados para resolução de nomes de filiais.

Usado pelos módulos de NPS e de faturamento para interpretar
o nome de filial informado pelo usuário, mesmo com pequenas
variações de escrita ou erros de digitação.
"""
import difflib
import unicodedata


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
        nome = nome.replace(
            palavra,
            " ",
        )

    nome = " ".join(
        nome.split()
    )

    return nome


def encontrar_filial_mais_proxima(
    nome_procurado_normalizado: str,
    nomes_disponiveis: list[str],
    limiar: float = 0.8,
) -> str | None:
    """
    Encontra, entre os nomes disponíveis, o que melhor
    corresponde ao nome procurado (já normalizado).

    Primeiro tenta uma correspondência direta (substring).
    Se não encontrar, usa similaridade textual e aceita
    o melhor resultado apenas se atingir o limiar mínimo.

    Retorna o nome original (não normalizado) encontrado,
    ou None caso nenhuma correspondência seja aceitável.
    """

    melhor_similaridade = -1.0
    melhor_nome = None

    for nome_original in nomes_disponiveis:
        nome_normalizado = normalizar_nome_filial(nome_original)

        if (
            nome_procurado_normalizado in nome_normalizado
            or nome_normalizado in nome_procurado_normalizado
        ):
            return nome_original

        similaridade = difflib.SequenceMatcher(
            None,
            nome_procurado_normalizado,
            nome_normalizado,
        ).ratio()

        if similaridade > melhor_similaridade:
            melhor_similaridade = similaridade
            melhor_nome = nome_original

    if melhor_nome is not None and melhor_similaridade >= limiar:
        return melhor_nome

    return None
