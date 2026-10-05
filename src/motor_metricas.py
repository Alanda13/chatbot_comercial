"""
Motor de métricas.

Funções PURAS: recebem números, devolvem números. Nunca tocam em banco,
nunca chamam a IA. Isso é o que garante que o Gemini jamais precise (nem
possa) fazer conta — ele só recebe o resultado já pronto daqui.

Toda fórmula do documento do gestor mora aqui, com nome explícito para
poder ser referenciada pelo campo "formula"/"derivados" em catalogo.py.
Adaptado do rascunho original do gestor (Downloads\\motor_metricas.py).
"""
import calendar
from datetime import date, timedelta
from typing import Optional

from src.variacao_utils import calcular_diferenca_percentual


def calcular_dias_uteis_restantes(ano: int, mes: int) -> Optional[int]:
    """
    Conta os dias úteis (segunda a sexta) restantes no mês, a partir
    de hoje (inclusive), sem considerar feriados. Só faz sentido para
    o mês/ano atual — para qualquer outro período, retorna None (não
    há "necessidade diária" de um mês que já passou ou que ainda nem
    começou).
    """
    hoje = date.today()

    if (ano, mes) != (hoje.year, hoje.month):
        return None

    ultimo_dia = calendar.monthrange(ano, mes)[1]
    fim_do_mes = date(ano, mes, ultimo_dia)

    dias_uteis = 0
    dia_atual = hoje

    while dia_atual <= fim_do_mes:
        if dia_atual.weekday() < 5:
            dias_uteis += 1
        dia_atual += timedelta(days=1)

    return dias_uteis


def calcular_atingimento_meta(
    faturamento: Optional[float], meta: Optional[float]
) -> Optional[float]:
    """% Meta = Faturamento / Meta"""
    if not meta or faturamento is None:
        return None
    return round((faturamento / meta) * 100, 2)


def calcular_desconto(
    desconto_concedido: Optional[float], fat_tabela: Optional[float]
) -> Optional[float]:
    """
    % Desconto = Desconto concedido / Fat. Tabela

    Desconto concedido = soma de (preço de tabela − preço vendido) só
    dos itens vendidos ABAIXO da tabela (campo VLDESCONTO do WinThor) —
    venda acima da tabela conta zero, não abate o desconto dos outros
    itens (mesmo critério da rotina 8302).
    """
    if not fat_tabela or desconto_concedido is None:
        return None
    # 4 casas: com 2, clientes que compram muito e quase não têm desconto
    # empatavam todos em 0,00% e "quem menos teve desconto" saía em ordem
    # aleatória. A tela formata com 2 casas ("menos de 0,01%").
    return round((desconto_concedido / fat_tabela) * 100, 4)


def calcular_inadimplencia(
    valor_inadimplente: Optional[float], faturamento_liquido: Optional[float]
) -> Optional[float]:
    """% Inadimplência = Valor Inadimplente / Faturamento Líquido"""
    if not faturamento_liquido:
        return None
    return round((valor_inadimplente / faturamento_liquido) * 100, 2)


def calcular_crescimento(
    atual: Optional[float], anterior: Optional[float]
) -> Optional[float]:
    """
    % de crescimento entre dois períodos. Delega para
    variacao_utils.calcular_diferenca_percentual — a mesma fórmula que
    NPS e Metas já usam pra "variação em relação ao anterior" — em vez
    de reimplementar a mesma conta uma terceira vez.
    """
    _, percentual = calcular_diferenca_percentual(anterior, atual)
    return percentual


def calcular_valor_faltante(
    meta: Optional[float], realizado: Optional[float]
) -> Optional[float]:
    if meta is None or realizado is None:
        return None
    return round(max(meta - realizado, 0), 2)


def calcular_necessidade_diaria(
    valor_faltante: Optional[float], dias_restantes: Optional[int]
) -> Optional[float]:
    if not dias_restantes or valor_faltante is None:
        return None
    return round(valor_faltante / dias_restantes, 2)


def calcular_nps(
    promotores: Optional[float],
    detratores: Optional[float],
    total_respostas: Optional[float],
) -> Optional[float]:
    """NPS = % de promotores − % de detratores (sobre o total de respostas)."""
    if not total_respostas:
        return None
    return round((promotores - detratores) / total_respostas * 100, 2)


def calcular_toneladas(peso_liquido: Optional[float]) -> Optional[float]:
    """Converte peso líquido (quilos) para toneladas."""
    if peso_liquido is None:
        return None
    return round(peso_liquido / 1000, 2)


def calcular_participacao(
    valor_item: Optional[float], valor_total: Optional[float]
) -> Optional[float]:
    """Ex.: participação de um cliente/produto no faturamento total"""
    if not valor_total:
        return None
    return round((valor_item / valor_total) * 100, 2)


FORMULAS = {
    "calcular_atingimento_meta": calcular_atingimento_meta,
    "calcular_desconto": calcular_desconto,
    "calcular_inadimplencia": calcular_inadimplencia,
    "calcular_crescimento": calcular_crescimento,
    "calcular_valor_faltante": calcular_valor_faltante,
    "calcular_necessidade_diaria": calcular_necessidade_diaria,
    "calcular_participacao": calcular_participacao,
    "calcular_toneladas": calcular_toneladas,
    "calcular_nps": calcular_nps,
}
