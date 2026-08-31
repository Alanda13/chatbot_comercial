"""
Serviço responsável pela comunicação com a API do Gemini.
"""
import json
import os
from datetime import date

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import ValidationError

from src.prompts import PROMPT_SISTEMA
from src.schemas import SolicitacaoFerramenta
from src.tool_manager import gerar_catalogo_ferramentas
from src.exceptions import IAIndisponivelError
from src.logger import obter_logger

load_dotenv()

logger = obter_logger(__name__)

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
        f"\n\nData atual: {date.today().isoformat()}"
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
        resultado,
        ensure_ascii=False,
        indent=2,
        default=str,
    )

    historico_formatado = _formatar_historico_para_resposta(historico)

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
- MESMO quando a resposta for um único valor, sempre responda com
  uma frase completa que identifique a que aquele valor se refere
  (indicador, filial/RCA e período, conforme o que foi perguntado).
  NUNCA responda só com o número isolado, sem frase — isso soa como
  falha do sistema, não como uma resposta de atendimento. Exemplo:
  em vez de responder apenas "R$ 254.017,32", responda algo como
  "O faturamento do RCA José Felipe Pires em julho de 2025 foi de
  R$ 254.017,32."
- Se a pergunta atual for curta ou incompleta (ex: "e em julho?", "e
  a filial Tibiri?", "e em 2024?") e não repetir qual indicador o
  usuário quer (toneladas, venda bruta, desconto, quantidade de
  notas, etc.), use o "Histórico recente da conversa" abaixo para
  identificar qual indicador foi perguntado antes, e responda com o
  MESMO indicador — nunca troque para o faturamento (venda líquida)
  por padrão quando o assunto da conversa era outro indicador.

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
- Quando o usuário pedir apenas o valor de um indicador, não
  acrescente outros indicadores que ele não pediu (ex: venda bruta,
  desconto, peso líquido, quantidade de notas) — mas sempre em uma
  frase completa (ver regra acima), nunca como número isolado.
- Quando o usuário pedir os valores de diferentes períodos,
  apresente os valores solicitados.
- Não confunda "comparar valores" com "calcular crescimento".
- Se a pergunta pedir crescimento ou queda, não limite a resposta
  à apresentação dos valores inicial e final.

REGRAS PARA QUANDO A CONSULTA FOI FEITA POR RCA:
- Se "filtros_aplicados" tiver o campo "rcas_identificados", a
  consulta foi feita informando o nome do vendedor (não o código), e
  o sistema resolveu esse nome para um RCA específico.
- Nesse caso, SEMPRE mencione o nome e o código do RCA na resposta
  (ex: "O faturamento do RCA Alfredo Sousa (código 8403) em 2025 foi
  de..."), mesmo que o usuário só tenha perguntado pelo nome — isso
  garante que a pessoa que perguntou confirme que é o vendedor
  correto.
- Se, além do RCA, a consulta também tiver sido filtrada por uma
  filial específica (campo "filiais" em "filtros_aplicados" com uma
  única filial), termine a resposta perguntando, de forma breve, se
  o usuário quer o faturamento total desse RCA (somando todas as
  filiais em que ele vende) ou o faturamento em outra filial. Isso é
  comum porque quem usa o chatbot muitas vezes é gerente de uma loja
  e pergunta pelo RCA "da sua loja", mas pode querer o total depois.
  Exemplo de complemento: "Quer que eu consulte o faturamento total
  desse RCA em todas as filiais, ou de outra filial específica?"
- Se "rcas_identificados" tiver MAIS DE UM item com o mesmo nome de
  vendedor mas códigos diferentes, e NENHUMA filial específica tiver
  sido informada em "filtros_aplicados", isso significa que o
  sistema somou o faturamento de todos os RCAs com esse nome (um em
  cada filial em que ele aparece), porque o usuário não restringiu a
  uma loja. Deixe isso claro na resposta, citando quantas filiais
  foram somadas, e ofereça consultar uma filial específica. Exemplo:
  "O faturamento total do RCA André Alves, somando as 13 filiais em
  que ele aparece, em 2025 foi de R$ ... . Quer que eu consulte só
  uma filial específica?"

REGRAS PARA A FERRAMENTA "verificar_rca":
- Essa ferramenta só confirma se um RCA existe — ela NUNCA traz
  valor de faturamento, porque foi usada sem período (o usuário
  mencionou o RCA antes de informar quando).
- Se o resultado tiver "encontrado": true, apresente o(s) nome(s) e
  código(s) em "rcas_identificados" e pergunte qual período o
  usuário deseja consultar para aquele RCA. Exemplo: "Encontrei o
  RCA Alfredo Sousa (código 8403). Qual período você deseja
  consultar? Por exemplo: julho de 2025 ou o ano de 2025."
- Se o resultado tiver "encontrado": false, informe diretamente que
  o RCA não foi encontrado (usando a "mensagem" do sistema como
  base, reformulada de forma natural) — NÃO peça o período nesse
  caso, já que não faz sentido pedir período de um RCA que não
  existe. Exemplo: "Não encontrei nenhum RCA com o código 4567.
  Verifique o código informado e tente novamente."

REGRAS PARA QUANDO NÃO HÁ DADOS ("encontrado": false):
- NUNCA repita literalmente o texto do campo "mensagem" retornado
  pelo sistema (ex: "Nenhum dado encontrado para os filtros
  informados.") — isso soa como um erro técnico, não como uma
  resposta de atendimento.
- Em vez disso, reformule de forma natural e específica, citando a
  filial e o período/data que constam em "filtros_aplicados" (quando
  disponíveis). Exemplo: em vez de "Nenhum dado encontrado para os
  filtros informados.", responda algo como "Não há faturamento
  registrado para a filial Campos Sales em 26/08/2026."
- Não invente o motivo da ausência de dados (ex: não afirme que a
  loja estava fechada ou que foi feriado) a menos que essa
  informação esteja explicitamente nos dados retornados — apenas
  informe que não há registro para o período/filtro solicitado.
- SEMPRE termine orientando o usuário sobre o próximo passo, de
  forma breve, com base no que a mensagem do sistema sugerir. Por
  exemplo: se a mensagem indicar que uma filial não foi encontrada,
  peça para verificar a grafia do nome ou informar outra filial; se
  indicar que faltou um período, peça para informar o período; se
  indicar que não há dados para o filtro pedido, sugira tentar outro
  período ou outra filial. Adapte a orientação ao conteúdo real da
  mensagem — nunca deixe a resposta terminar apenas dizendo que algo
  não foi encontrado, sem indicar o que o usuário pode fazer a
  seguir.

REGRAS PARA QUANDO HÁ MAIS DE UM RCA COM O MESMO NOME (mensagem
contendo "Encontrei mais de um RCA"):
- Essa mensagem lista cada RCA candidato com nome, código e filial.
  NUNCA resuma ou omita o código de nenhum candidato — o código é a
  ÚNICA forma de o usuário indicar qual RCA ele quer, já que os
  nomes são iguais ou parecidos entre si.
- Liste TODOS os candidatos, um por um, sempre no formato "nome
  (código NÚMERO, filial NOME_DA_FILIAL)" — nunca resuma para "nas
  filiais X, Y e Z" sem os códigos, isso torna a resposta inútil.
- Termine pedindo para o usuário informar o código do RCA desejado.

REGRAS PARA QUANDO OS DADOS FORAM TRUNCADOS (campo "aviso"):
- Se os dados retornados tiverem um campo "aviso", isso significa
  que a consulta trouxe muitos resultados e só uma parte foi
  enviada. Responda normalmente com os dados disponíveis, e ao
  final, informe de forma breve que a lista foi limitada e sugira
  ao usuário pedir um filtro mais específico (ex: uma filial, um
  RCA ou um período menor) para ver o restante.

FORMATAÇÃO:
- Valores monetários devem ser apresentados em reais, no formato
  brasileiro: R$ 1.234.567,89.
- Percentuais devem ser apresentados com duas casas decimais.
- Toneladas devem ser apresentadas no formato brasileiro, com duas
  casas decimais e a palavra "toneladas" (ex: 1.020,41 toneladas).
- Nunca utilize crases (`) para destacar valores, números, datas
  ou percentuais.
- Nunca utilize formatação de código inline.
- Não escreva "R`" ou "`R$".
- Não coloque valores monetários, percentuais ou números entre crases.
- Não apresente campos como venda bruta, desconto, peso líquido/toneladas
  ou quantidade de notas se eles não forem solicitados pelo usuário.
- Não mencione nomes de funções Python, ferramentas internas,
  JSON, banco de dados ou detalhes técnicos do sistema.

Histórico recente da conversa:
{historico_formatado}

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
            logger.warning(
                "Falha ao consultar o modelo %s: %s", modelo, error
            )

    if resposta is None or not resposta.text:
        raise IAIndisponivelError(
            "Não foi possível gerar a resposta final neste momento."
        ) from ultimo_erro

    return resposta.text.strip().replace("`", "")