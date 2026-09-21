"""
Ferramentas do módulo de faturamento.

Este arquivo faz a ponte entre os nomes informados pela IA
e as consultas de faturamento.
"""
from src.faturamento_diario_data import verificar_rca
from src.filiais import resolver_nome_filial


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
