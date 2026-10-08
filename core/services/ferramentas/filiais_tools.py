"""
Ferramenta para listar as filiais atendidas pelo chatbot.
"""
from core.repositories.filiais_repository import listar_filiais


def executar_listar_filiais(argumentos: dict) -> dict:
    """
    Retorna a lista de filiais existentes atendidas pelo chatbot,
    junto com a quantidade total.
    """
    filiais = listar_filiais()

    return {
        "quantidade_filiais": len(filiais),
        "filiais": filiais,
    }
