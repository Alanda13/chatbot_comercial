"""
Serviço responsável pela comunicação com a API do Gemini.
"""

import json
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import ValidationError

from src.prompts import PROMPT_SISTEMA
from src.schemas import SolicitacaoFerramenta
from src.tool_manager import gerar_catalogo_ferramentas


load_dotenv()


def criar_cliente_gemini() -> genai.Client:
    """
    Cria o cliente do Gemini usando a chave armazenada no arquivo .env.
    """

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise ValueError(
            "A variável GEMINI_API_KEY não foi encontrada no arquivo .env."
        )

    return genai.Client(api_key=api_key)


def interpretar_pergunta(
    pergunta: str,
    historico: list[dict[str, str]] | None = None,
) -> SolicitacaoFerramenta:
    """
    Envia a pergunta ao Gemini e retorna uma solicitação validada.

    O Gemini apenas interpreta a intenção do usuário.
    Ele não acessa o banco e não executa ferramentas.
    """

    if not pergunta.strip():
        raise ValueError("A pergunta não pode estar vazia.")

    catalogo = gerar_catalogo_ferramentas()
    historico = historico or []

    texto_historico = "\n".join(
        f"{mensagem['papel']}: {mensagem['conteudo']}"
        for mensagem in historico
    )

    conteudo = f"""
{PROMPT_SISTEMA}

Ferramentas disponíveis:

{catalogo}

Histórico relevante da conversa:

{texto_historico or "Nenhum histórico disponível."}

Pergunta atual do usuário:

{pergunta}
"""
    cliente = criar_cliente_gemini()

    resposta = cliente.models.generate_content(
        model="gemini-3.5-flash",
        contents=conteudo,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0,
        ),
    )

    if not resposta.text:
        raise RuntimeError("O Gemini não retornou uma resposta.")

    try:
        dados = json.loads(resposta.text)

    except json.JSONDecodeError as error:
        raise ValueError(
            "O Gemini não retornou um JSON válido."
        ) from error

    try:
        return SolicitacaoFerramenta.model_validate(dados)

    except ValidationError as error:
        print("\n=== JSON RECEBIDO DO GEMINI ===")
        print(json.dumps(dados, indent=2, ensure_ascii=False))

        print("\n=== ERRO DE VALIDAÇÃO ===")
        print(error)

        raise ValueError(
               "O JSON retornado pelo Gemini não segue o contrato esperado."
        ) from error