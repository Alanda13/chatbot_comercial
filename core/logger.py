"""
Configuração central de logging do Chatbot Comercial.
"""
import logging
import os

_CONFIGURADO = False


def obter_logger(nome: str) -> logging.Logger:
    """
    Retorna um logger configurado para o módulo informado.

    O nível pode ser ajustado pela variável de ambiente LOG_LEVEL
    (padrão: INFO).
    """
    global _CONFIGURADO

    if not _CONFIGURADO:
        logging.basicConfig(
            level=os.getenv("LOG_LEVEL", "INFO"),
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )
        _CONFIGURADO = True

    return logging.getLogger(nome)
