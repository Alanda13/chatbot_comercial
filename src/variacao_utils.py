"""
Cálculo de variação (diferença + percentual) entre um valor e o
anterior — mês anterior, ano anterior, mesmo mês do ano anterior etc.
Extraído porque esse cálculo e o loop de "agrupar, ordenar e comparar
com o item anterior" se repetiam em cada indicador (NPS, metas...); um
indicador novo só chama as funções daqui, não reescreve nenhum dos
dois.
"""


def calcular_diferenca_percentual(valor_anterior, valor_atual):
    """
    Diferença e percentual de variação de `valor_anterior` pra
    `valor_atual`. (None, None) quando falta um dos dois valores. Se o
    anterior é zero, a diferença existe mas o percentual não (não dá
    pra tirar percentual em cima de zero) — ex: um NPS que foi de 0
    a 75 subiu 75 pontos.
    """
    if valor_anterior is None or valor_atual is None:
        return None, None

    diferenca = round(valor_atual - valor_anterior, 2)

    if valor_anterior == 0:
        return diferenca, None

    percentual = round(
        (valor_atual - valor_anterior) / abs(valor_anterior) * 100, 2
    )
    return diferenca, percentual


def calcular_variacao_sequencial(
    itens,
    campo_valor,
    sufixo,
    chave_grupo=None,
    chave_ordem=None,
    incluir_valor_anterior_como=None,
):
    """
    Preenche em cada item de `itens` (lista de dicts) a variação de
    `campo_valor` em relação ao item anterior do MESMO GRUPO — grupo é
    o que `chave_grupo(item)` devolver (ex: mesma filial); sem
    `chave_grupo`, todo mundo é um grupo só. Grava "diferenca_{sufixo}"
    e "percentual_{sufixo}" (None no primeiro item de cada grupo), e
    também o valor bruto anterior em `incluir_valor_anterior_como`,
    se informado.

    Se a ordem de `itens` não for a cronológica esperada, passe
    `chave_ordem` pra essa função reordenar antes de calcular. Modifica
    os itens in-place e devolve a mesma lista.
    """
    if chave_ordem is not None:
        itens.sort(key=chave_ordem)

    if chave_grupo is None:
        chave_grupo = lambda item: None

    campo_diferenca = f"diferenca_{sufixo}"
    campo_percentual = f"percentual_{sufixo}"

    valor_anterior_por_grupo = {}

    for item in itens:
        chave = chave_grupo(item)
        valor_anterior = valor_anterior_por_grupo.get(chave)
        valor_atual = item[campo_valor]

        item[campo_diferenca], item[campo_percentual] = (
            calcular_diferenca_percentual(valor_anterior, valor_atual)
        )

        if incluir_valor_anterior_como:
            item[incluir_valor_anterior_como] = valor_anterior

        if valor_atual is not None:
            valor_anterior_por_grupo[chave] = valor_atual

    return itens
