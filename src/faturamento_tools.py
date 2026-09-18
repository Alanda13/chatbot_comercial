"""
Ferramentas do módulo de faturamento.

Este arquivo faz a ponte entre os nomes informados pela IA
e as consultas de faturamento.
"""
from src.faturamento_data import listar_filiais_faturamento
from src.faturamento_diario_data import verificar_rca
from src.filial_utils import (
    encontrar_filial_mais_proxima,
    normalizar_nome_filial,
)

def resolver_nome_filial(nome_informado: str) -> str:
    """
    Encontra o nome correto da filial na base de faturamento.
    """

    filiais = listar_filiais_faturamento()

    if not filiais:
        raise ValueError(
            "Nenhuma filial foi encontrada "
            "na base de faturamento."
        )

    nome_procurado = normalizar_nome_filial(
        nome_informado
    )

    filial_encontrada = encontrar_filial_mais_proxima(
        nome_procurado,
        filiais,
    )

    if filial_encontrada is None:
        raise ValueError(
            f"A filial '{nome_informado}' não foi encontrada."
        )

    return filial_encontrada


def executar_verificar_rca(argumentos: dict) -> dict:
    """
    Verifica se um RCA (por nome ou código) existe, sem exigir
    período — usada para confirmar o RCA antes de pedir o período ao
    usuário.
    """

    rca = argumentos.get("rca")

    if not rca:
        raise ValueError(
            "Informe o nome ou o código do RCA que deseja verificar."
        )

    filiais = argumentos.get("filiais")

    filiais_resolvidas = None

    if filiais:
        filiais_resolvidas = []

        for filial in filiais:
            nome_resolvido = resolver_nome_filial(filial)

            if nome_resolvido not in filiais_resolvidas:
                filiais_resolvidas.append(nome_resolvido)

    return verificar_rca(rca, filiais=filiais_resolvidas)
