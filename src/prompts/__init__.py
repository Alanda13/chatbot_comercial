"""
Prompt do sistema usado pelo Chatbot Comercial.

O conteúdo é dividido em módulos por assunto (regras gerais, NPS,
faturamento, ações/formato) apenas para facilitar a manutenção do
prompt — o texto final enviado à IA é idêntico ao de antes da divisão.
"""
from src.prompts.base import PROMPT_BASE
from src.prompts.nps import PROMPT_NPS
from src.prompts.faturamento import PROMPT_FATURAMENTO
from src.prompts.metas import PROMPT_METAS
from src.prompts.rodape import PROMPT_RODAPE

PROMPT_SISTEMA = (
    PROMPT_BASE
    + PROMPT_NPS
    + PROMPT_FATURAMENTO
    + PROMPT_METAS
    + PROMPT_RODAPE
)
