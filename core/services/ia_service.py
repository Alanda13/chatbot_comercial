"""
Serviço responsável pela comunicação com a API do Gemini.
"""
import json
import os
from datetime import date, timedelta

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import ValidationError

from core.services.conferencia_service import numeros_inventados, valores_permitidos
from core.services.prompts import PROMPT_SISTEMA
from core.services.prompts.resposta import regras_da_resposta
from core.models import SolicitacaoFerramenta
from core.services.ferramentas.tool_manager import gerar_catalogo_ferramentas
from core.exceptions import IAIndisponivelError
from core.logger import obter_logger

load_dotenv()

logger = obter_logger(__name__)

_DIAS_DA_SEMANA = (
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
)


def calendario_recente(hoje: date | None = None) -> str:
    """
    A data de cada dia desta semana e da semana passada (segunda a
    domingo). Sem isso a IA não sabia que "sexta da semana passada" era
    02/10/2026 e consultava a semana inteira, respondendo como se fosse
    a sexta.
    """
    hoje = hoje or date.today()
    segunda = hoje - timedelta(days=hoje.weekday())

    def semana(inicio: date) -> str:
        return "; ".join(
            f"{_DIAS_DA_SEMANA[i]} {(inicio + timedelta(days=i)).strftime('%d/%m/%Y')}"
            for i in range(7)
        )

    return (
        f"Hoje é {_DIAS_DA_SEMANA[hoje.weekday()]}, {hoje.strftime('%d/%m/%Y')}.\n"
        f"Esta semana: {semana(segunda)}.\n"
        f"Semana passada: {semana(segunda - timedelta(days=7))}.\n"
        "Um dia da semana citado (ex: 'sexta da semana passada') é UM dia: "
        "use periodo_personalizado com data_inicial = data_final = esse dia, "
        "nunca a semana inteira."
    )

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

def _montar_historico_gemini(
    historico: list[dict[str, str]],
) -> list[types.Content]:
    """
    Converte o histórico de mensagens da conversa (papel/conteudo)
    para o formato de turnos estruturados esperado pela API do
    Gemini, em vez de um texto simples concatenado no prompt.
    """
    return [
        types.Content(
            role="model" if mensagem["papel"] == "assistant" else "user",
            parts=[types.Part(text=mensagem["conteudo"])],
        )
        for mensagem in historico
    ]


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

    instrucao_sistema = (
        f"{PROMPT_SISTEMA}\n\nFerramentas disponíveis:\n\n{catalogo}"
        f"\n\nData atual: {date.today().isoformat()}\n{calendario_recente()}"
    )
    conteudos_historico = _montar_historico_gemini(historico)

    cliente = criar_cliente_gemini()

    # Modelos válidos da API
    modelo_principal = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    modelo_reserva = os.getenv("GEMINI_MODEL_FALLBACK", "gemini-1.5-flash")

    modelos = [modelo_principal, modelo_reserva]

    ultimo_erro = None

    # A validação do JSON acontece dentro do loop: se um modelo
    # devolver uma resposta malformada ou fora do contrato, tentamos
    # o próximo modelo antes de desistir, em vez de falhar de cara.
    for modelo in modelos:
        try:
            chat = cliente.chats.create(
                model=modelo,
                history=conteudos_historico,
                config=types.GenerateContentConfig(
                    system_instruction=instrucao_sistema,
                    response_mime_type="application/json",
                ),
            )
            resposta = chat.send_message(pergunta)

            if not resposta or not resposta.text:
                continue

            dados = json.loads(resposta.text)

            return SolicitacaoFerramenta.model_validate(dados)

        except json.JSONDecodeError as error:
            ultimo_erro = error
            logger.warning(
                "Modelo %s não retornou um JSON válido: %r",
                modelo,
                resposta.text,
            )
        except ValidationError as error:
            ultimo_erro = error
            logger.warning(
                "Modelo %s retornou JSON fora do contrato esperado: %s",
                modelo,
                json.dumps(dados, ensure_ascii=False),
            )
        except Exception as error:
            ultimo_erro = error
            logger.warning(
                "Falha ao consultar o modelo %s: %s", modelo, error
            )

    raise IAIndisponivelError(
        "Não foi possível interpretar a pergunta neste momento. "
        "Os modelos disponíveis podem estar temporariamente "
        "sobrecarregados ou retornando respostas inválidas. "
        "Tente novamente mais tarde."
    ) from ultimo_erro


def _formatar_historico_para_resposta(
    historico: list[dict[str, str]] | None,
    limite: int = 6,
) -> str:
    """
    Formata as últimas mensagens da conversa em texto simples, para
    dar contexto à etapa de formulação da resposta final.

    Sem isso, um follow-up curto (ex: "e em julho?") que não repete
    o indicador perguntado antes (toneladas, venda bruta, etc.) fica
    sem contexto nessa etapa — que é uma chamada separada da que
    interpreta a pergunta, sem acesso ao histórico da conversa.
    """
    if not historico:
        return "Nenhuma mensagem anterior nesta conversa."

    mensagens_recentes = historico[-limite:]

    linhas = [
        f"{'Usuário' if mensagem['papel'] == 'user' else 'Assistente'}: "
        f"{mensagem['conteudo']}"
        for mensagem in mensagens_recentes
    ]

    return "\n".join(linhas)


# Na tentativa sem execução de código, a IA não pode fazer conta nenhuma
# (sem isso, ela calculava "de cabeça" o % dos grupos e errava).
_SEM_CODIGO = (
    "\n\nATENÇÃO: nesta resposta você NÃO pode executar código. Então NÃO "
    "calcule nada (nem % de grupo, nem média, nem total): use só os números "
    "que estão nos dados, item por item."
)

_RESPOSTA_SEM_NUMEROS_CONFERIDOS = (
    "Não consegui montar essa análise com segurança agora — os números que "
    "eu calculei não bateram com os dados do sistema. Os valores de cada "
    "item estão na tabela abaixo. Se quiser, tente de novo em instantes ou "
    "pergunte sobre um item específico."
)


def _saidas_de_codigo(resposta) -> list[str]:
    """O que o código executado pela IA imprimiu (pra conferir os números)."""
    saidas = []

    for candidato in getattr(resposta, "candidates", None) or []:
        conteudo = getattr(candidato, "content", None)
        for parte in getattr(conteudo, "parts", None) or []:
            resultado = getattr(parte, "code_execution_result", None)
            if resultado is not None and getattr(resultado, "output", None):
                saidas.append(resultado.output)

    return saidas


def _percentuais_como_na_tabela(dado):
    """
    Percentuais com 2 casas, iguais aos da tabela, no que vai pra IA: com 4
    casas ela CORTAVA em vez de arredondar (5,6574 → "5,65", a tabela diz
    5,66%) e a conferência barrava a resposta. Abaixo de 0,01 fica como
    está (vira "menos de 0,01%").
    """
    if isinstance(dado, dict):
        return {
            chave: (
                round(valor, 2)
                if "percentual" in str(chave) and isinstance(valor, float) and abs(valor) >= 0.01
                else _percentuais_como_na_tabela(valor)
            )
            for chave, valor in dado.items()
        }
    if isinstance(dado, list):
        return [_percentuais_como_na_tabela(item) for item in dado]
    return dado


def gerar_resposta_final(
    pergunta: str,
    nome_ferramenta: str,
    resultado: dict,
    historico: list[dict[str, str]] | None = None,
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
        _percentuais_como_na_tabela(resultado),
        ensure_ascii=False,
        indent=2,
        default=str,
    )

    historico_formatado = _formatar_historico_para_resposta(historico)

    prompt_resposta = f"""
Você é o assistente comercial da Ferronorte.

Sua tarefa agora é responder à pergunta do usuário utilizando
EXCLUSIVAMENTE os dados retornados pelo sistema.

{regras_da_resposta(resultado, nome_ferramenta)}

Histórico recente da conversa:
{historico_formatado}

Data atual: {date.today().isoformat()}
{calendario_recente()}

Pergunta original do usuário:
{pergunta}

Ferramenta utilizada:
{nome_ferramenta}

Dados reais retornados pelo sistema:
{dados_formatados}

Responda diretamente ao usuário.
"""
    ultimo_erro = None
    ultimo_texto = None

    # Com "executar código": contas de análise (% de um grupo, média,
    # mediana, correlação) são feitas por Python sobre os dados do sistema,
    # não "de cabeça". Se o recurso falhar (outro modelo, outra chave),
    # tenta sem ele: a resposta sai sem contas, nunca dá erro.
    com_codigo = types.GenerateContentConfig(
        tools=[types.Tool(code_execution=types.ToolCodeExecution())],
        temperature=0,
    )
    # Trava contra número inventado: o código calculava certo, mas o texto
    # às vezes saía com outro número (06/10/2026: "sem Parnaíba" 2,70% no
    # código e 2,75%/2,23%/3,17% no texto). Todo número do texto tem que
    # existir nos dados (resultado, saída do código, pergunta, histórico);
    # senão tenta de novo e, por último, sem execução de código.
    dados_conhecidos = (resultado, pergunta, historico or [])
    tentativas = [com_codigo, com_codigo, None]

    for modelo in modelos:
        for configuracao in tentativas:
            try:
                resposta = cliente.models.generate_content(
                    model=modelo,
                    contents=(
                        prompt_resposta if configuracao is not None
                        else prompt_resposta + _SEM_CODIGO
                    ),
                    config=configuracao,
                )
            except Exception as error:
                ultimo_erro = error
                logger.warning(
                    "Falha ao consultar o modelo %s (%s): %s", modelo,
                    "com execução de código" if configuracao else "sem ferramentas",
                    error,
                )
                continue

            texto = (getattr(resposta, "text", None) or "").strip().replace("`", "")
            if not texto:
                continue

            ultimo_texto = texto
            permitidos = valores_permitidos(
                *dados_conhecidos, saidas_de_codigo=_saidas_de_codigo(resposta)
            )
            inventados = numeros_inventados(texto, permitidos)

            if not inventados:
                return texto

            logger.warning(
                "Resposta com número(s) que não existem nos dados %s — "
                "gerando de novo.", inventados,
            )

    if ultimo_texto is None:
        raise IAIndisponivelError(
            "Não foi possível gerar a resposta final neste momento."
        ) from ultimo_erro

    # Nenhuma tentativa passou na conferência: não mostra número nenhum
    # (a tabela com os números do sistema continua aparecendo na tela).
    return _RESPOSTA_SEM_NUMEROS_CONFERIDOS
