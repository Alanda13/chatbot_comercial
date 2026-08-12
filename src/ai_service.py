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

# Carrega as variáveis armazenadas no arquivo .env.
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

    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=10_000,
            retry_options=types.HttpRetryOptions(
                attempts=1,
                initial_delay=1,
                max_delay=2,
                exp_base=2,
                http_status_codes=[
                    429,
                    500,
                    502,
                    503,
                    504,
                ],
            ),
        ),
    )

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

    # Os nomes dos modelos ficam no .env.
    # Caso não estejam preenchidos, estes valores serão usados.
    modelo_principal = os.getenv(
        "GEMINI_MODEL",
        "gemini-3.5-flash-lite",
    )

    modelo_reserva = os.getenv(
        "GEMINI_MODEL_FALLBACK",
        "gemini-3.6-flash",
    )

    modelos = [
        modelo_principal,
        modelo_reserva,
    ]

    resposta = None
    ultimo_erro = None

    # Tenta primeiro o modelo principal.
    # Se falhar, tenta automaticamente o modelo reserva.
    for modelo in modelos:
        try:
            resposta = cliente.models.generate_content(
                model=modelo,
                contents=conteudo,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )

            break

        except Exception as error:
            ultimo_erro = error

    if resposta is None:
        raise RuntimeError(
            "Não foi possível acessar o Gemini neste momento. "
            "Os modelos disponíveis podem estar temporariamente "
            "sobrecarregados. Tente novamente mais tarde."
        ) from ultimo_erro

    if not resposta.text:
        raise RuntimeError(
            "O Gemini não retornou uma resposta."
        )

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
        print(
            json.dumps(
                dados,
                indent=2,
                ensure_ascii=False,
            )
        )
        print("\n=== ERRO DE VALIDAÇÃO ===")
        print(error)

        raise ValueError(
            "O JSON retornado pelo Gemini não segue "
            "o contrato esperado."
        ) from error

def gerar_resposta_final(
    pergunta: str,
    nome_ferramenta: str,
    resultado: dict,
) -> str:
    """
    Gera a resposta final em linguagem natural usando
    exclusivamente os dados retornados pela ferramenta.
    """
    cliente = criar_cliente_gemini()

    modelo_principal = os.getenv(
        "GEMINI_MODEL",
        "gemini-3.5-flash-lite",
    )

    modelo_reserva = os.getenv(
        "GEMINI_MODEL_FALLBACK",
        "gemini-3.6-flash",
    )

    modelos = [
        modelo_principal,
        modelo_reserva,
    ]

    dados_formatados = json.dumps(
        resultado,
        ensure_ascii=False,
        indent=2,
        default=str,
    )

    prompt_resposta = f"""
Você é o assistente comercial da Ferronorte.

Sua tarefa agora é responder à pergunta do usuário utilizando
EXCLUSIVAMENTE os dados retornados pelo sistema.

REGRAS:
- Não invente dados.
- Não altere valores.
- Não crie informações que não estejam no resultado.
- Não faça novos cálculos sobre os dados.
- Responda em português do Brasil.
- Seja claro, objetivo e natural.
- Mostre principalmente a informação que o usuário pediu.
- Não precisa apresentar todos os campos disponíveis se eles
  não forem relevantes para a pergunta.
- Quando houver números decimais, apresente-os de forma adequada
  para leitura em português.
- Quando houver quantidade de registros/respostas, apresente-a
  de forma clara.
- Não mencione nomes de funções Python, ferramentas internas,
  JSON, banco de dados ou detalhes técnicos do sistema.

Pergunta original do usuário:
{pergunta}

Ferramenta utilizada:
{nome_ferramenta}

Dados reais retornados pelo sistema:
{dados_formatados}

Responda diretamente ao usuário.
"""
    resposta = None
    ultimo_erro = None

    for modelo in modelos:
        try:
            resposta = cliente.models.generate_content(
                model=modelo,
                contents=prompt_resposta,
            )

            break

        except Exception as error:
            ultimo_erro = error

    if resposta is None:
        raise RuntimeError(
            "Não foi possível gerar a resposta final neste momento."
        ) from ultimo_erro

    if not resposta.text:
        raise RuntimeError(
            "O Gemini não retornou uma resposta final."
        )

    return resposta.text.strip()