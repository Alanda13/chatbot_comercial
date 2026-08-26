"""
Ferramenta para listar as filiais existentes na base comercial.
"""
from src.faturamento_queries import listar_filiais_faturamento


def executar_listar_filiais(argumentos: dict) -> dict:
    """
    Retorna a lista de filiais existentes na base de faturamento,
    junto com a quantidade total.
    """
    filiais = listar_filiais_faturamento()

    return {
        "quantidade_filiais": len(filiais),
        "filiais": filiais,
    }
