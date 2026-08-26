"""
Exceções específicas do domínio do Chatbot Comercial.

Permitem distinguir falhas conhecidas e tratáveis (indisponibilidade
da IA, resposta fora do contrato, ferramenta inválida) de erros
verdadeiramente inesperados, tanto para tratamento quanto para logs.
"""


class ChatbotError(Exception):
    """Erro base para falhas conhecidas do chatbot."""


class IAIndisponivelError(ChatbotError):
    """A API do Gemini não respondeu com sucesso em nenhum modelo tentado."""


class RespostaInvalidaError(ChatbotError):
    """
    A IA retornou um conteúdo que não segue o contrato esperado
    (JSON inválido, schema não atendido, ação/ferramenta ausente).
    """


class FerramentaError(ChatbotError):
    """Erro ao validar ou executar uma ferramenta solicitada pela IA."""
