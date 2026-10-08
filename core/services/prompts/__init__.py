"""
Prompt do sistema usado pelo Chatbot Comercial.

O conteúdo é dividido em módulos por assunto (regras gerais, NPS,
faturamento, ações/formato) apenas para facilitar a manutenção do
prompt — o texto final enviado à IA é idêntico ao de antes da divisão.
"""
from core.services.prompts.base import PROMPT_BASE
from core.services.prompts.nps import PROMPT_NPS
from core.services.prompts.faturamento import PROMPT_FATURAMENTO
from core.services.prompts.metas import PROMPT_METAS
from core.services.prompts.meta_tonelada import PROMPT_META_TONELADA
from core.services.prompts.rodape import PROMPT_RODAPE

PROMPT_SISTEMA = (
    PROMPT_BASE
    + PROMPT_NPS
    + PROMPT_FATURAMENTO
    + PROMPT_METAS
    + PROMPT_META_TONELADA
    + PROMPT_RODAPE
)
