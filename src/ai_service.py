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
            timeout=30_000,
            retry_options=types.HttpRetryOptions(
                attempts=3,
                initial_delay=1,
                max_delay=5,
                exp_base=2,
                http_status_codes=[429, 500, 502, 503, 504],
            ),
        ),
    )


def interpretar_pergunta(
    pergunta: str,
    historico: list[dict[str, str]] | None = None,
) -> SolicitacaoFerramenta:
    """
    Envia a pergunta ao Gemini e retorna uma solicitação validada.
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

    # Modelos válidos da API
    modelo_principal = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    modelo_reserva = os.getenv("GEMINI_MODEL_FALLBACK", "gemini-1.5-flash")

    modelos = [modelo_principal, modelo_reserva]

    resposta = None
    ultimo_erro = None

    for modelo in modelos:
        try:
            resposta = cliente.models.generate_content(
                model=modelo,
                contents=conteudo,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            if resposta and resposta.text:
                break
        except Exception as error:
            ultimo_erro = error

    if resposta is None or not resposta.text:
        raise RuntimeError(
            "Não foi possível acessar o Gemini neste momento. "
            "Os modelos disponíveis podem estar temporariamente "
            "sobrecarregados. Tente novamente mais tarde."
        ) from ultimo_erro

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

    modelo_principal = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    modelo_reserva = os.getenv("GEMINI_MODEL_FALLBACK", "gemini-1.5-flash")

    modelos = [modelo_principal, modelo_reserva]

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
- Responda somente ao que foi solicitado pelo usuário.
- Não adicione informações que não sejam necessárias para responder à pergunta.
- Não invente dados.
- Não altere os valores retornados pelo sistema.
- Utilize exclusivamente os dados retornados pelo sistema.
- Responda em português do Brasil.
- Seja claro, objetivo e natural.
- Não utilize saudações desnecessárias como "Olá!".
- Não repita informações que o usuário não solicitou.

REGRAS PARA ANÁLISE E COMPARAÇÃO:
- Você pode realizar cálculos matemáticos simples utilizando
  exclusivamente os valores retornados pelo sistema, quando esses
  cálculos forem necessários para responder à pergunta do usuário.
- Quando o usuário perguntar "quanto cresceu", "quanto aumentou",
  "qual foi o crescimento" ou expressão equivalente, calcule:
  1. a diferença entre o valor final e o valor inicial;
  2. o percentual de crescimento em relação ao valor inicial.
- Quando o usuário perguntar "quanto caiu", "quanto reduziu",
  "qual foi a queda" ou expressão equivalente, calcule:
  1. a diferença entre o valor final e o valor inicial;
  2. o percentual de redução em relação ao valor inicial.
- Quando o usuário pedir uma comparação, apresente somente as
  informações necessárias para realizar a comparação.
- Quando o usuário pedir apenas o valor de um indicador, apresente
  somente esse valor.
- Quando o usuário pedir os valores de diferentes períodos,
  apresente os valores solicitados.
- Não confunda "comparar valores" com "calcular crescimento".
- Se a pergunta pedir crescimento ou queda, não limite a resposta
  à apresentação dos valores inicial e final.

FORMATAÇÃO:
- Valores monetários devem ser apresentados em reais, no formato
  brasileiro: R$ 1.234.567,89.
- Percentuais devem ser apresentados com duas casas decimais.
- Nunca utilize crases (`) para destacar valores, números ou qualquer
  parte da resposta.
- Não utilize formatação de código.
- Não apresente campos como venda bruta, desconto, peso líquido
  ou quantidade de notas se eles não forem solicitados pelo usuário.
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
            if resposta and resposta.text:
                break
        except Exception as error:
            ultimo_erro = error

    if resposta is None or not resposta.text:
        raise RuntimeError(
            "Não foi possível gerar a resposta final neste momento."
        ) from ultimo_erro

    return resposta.text.strip().replace("`", "")