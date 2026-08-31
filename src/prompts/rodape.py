"""
Ações permitidas e formato de resposta do prompt de sistema.
"""

PROMPT_RODAPE = """AÇÕES PERMITIDAS:

- "executar_ferramenta"
- "pedir_esclarecimento"
- "fora_do_escopo"
- "responder_com_historico"

Responda APENAS em JSON.

Formato obrigatório:

{
    "acao": "executar_ferramenta",
    "ferramenta": "nome_da_ferramenta",
    "argumentos": {},
    "mensagem": null
}
"""
