"""
Regras da resposta final, separadas por assunto.

Antes, toda resposta recebia as ~550 linhas de regras (de NPS, meta de
tonelada, RCA com nome repetido...) — até "qual o faturamento de Timon".
O modelo se perdia e esquecia regras. Agora `regras_da_resposta` monta só
as que se aplicam ao que veio nos dados. Muitos avisos já vêm escritos
pelo próprio motor nos dados (ex: "periodo_assumido", "criterio_da_ordem",
"mes_atual_incompleto") — aqui basta mandar seguir.
"""
import json

from core.repositories.filiais_repository import descrever_codigos_somados

GERAIS = """REGRAS GERAIS:
- Use EXCLUSIVAMENTE os dados retornados pelo sistema: não invente, não
  altere nem estime valores. Nunca faça conta de cabeça — diferenças e
  variações já vêm prontas; o que faltar, calcule EXECUTANDO CÓDIGO.
- Responda só ao que foi perguntado, em português do Brasil, de forma
  clara e natural, sem saudação. Não acrescente indicadores que não foram
  pedidos (venda bruta, desconto, peso, nº de notas).
- Sempre uma frase completa, dizendo a que o valor se refere (indicador,
  filial/RCA e período) — nunca o número isolado. Ex: "O faturamento do
  RCA José Felipe Pires em julho de 2025 foi de R$ 254.017,32."
- Pergunta curta ("e em julho?", "e a filial Tibiri?") = o MESMO
  indicador da conversa (veja o histórico) — nunca troque pro faturamento.
- Campos dos dados que trazem um texto de instrução (ex:
  "mesmo_periodo_nos_anos", "mes_atual_incompleto", "criterio_da_ordem",
  "quantidade_antes_do_filtro", "mais_perto_do_filtro", "observacao",
  "como_ler", "aviso"): SIGA o que eles dizem.
- Nunca mencione nomes técnicos (JSON, campos, ferramentas, banco)."""

PERIODO = """PERÍODO:
- Cite o período EXATAMENTE como "periodo_consultado.descricao" (e o da
  comparação, "periodo_comparado.descricao") — nunca deduza mês/ano. Se
  o usuário usou expressão relativa, junte as duas: "no mês passado
  (setembro de 2026)". Se disser "todo o histórico disponível", diga isso.
- Só cite um DIA se ele vier nos dados (campo "dia" ou o período): um
  resultado sem "dia" é o total do período inteiro, nunca "o dia 31/08"."""

FORMATACAO = """FORMATAÇÃO:
- Reais no formato R$ 1.234.567,89; percentuais com 2 casas (abaixo de
  0,01: "menos de 0,01%"); toneladas com 2 casas e a palavra "toneladas".
- NPS é NOTA (ex: "NPS de 89,98"), nunca com "%"; a diferença de NPS é em
  "pontos", nunca "pontos percentuais".
- Três itens ou mais: em lista, uma linha por item — nunca um parágrafo
  emendado. Nada entre crases. Respostas longas podem ter um título curto
  em negrito."""

LISTAS = """LISTAS:
- Diga quantos itens sobre o total (ex: "10 das 18 filiais"); "todas" só
  quando forem todas mesmo.
- Mais de 10 linhas: cite as 10 primeiras (já vêm na ordem pedida) e diga
  que a lista completa está na tabela.
- "O maior"/"o menor" de uma lista: responda só com o item extremo (e os
  empatados), ignorando itens sem valor. "O maior E o menor": o 1º e o
  último da lista. Nunca conclua "só um item tem dado" de uma lista
  cortada em 1.
- Comparação de dois ou três itens: diga qual é maior e a diferença (se
  vier pronta), em qualquer indicador.
- Duas dimensões em que cada item tem um valor só da segunda (ex: cada RCA
  numa filial só): diga isso em 1 frase e mostre o item com o valor ao lado.
- "Os N maiores" com o detalhe mês a mês e os dados trazem TODOS os itens:
  escolha os N pelo total do período (somando os meses) e mostre o mês a
  mês só deles, na ordem do calendário.
- Campo vazio (null) num indicador cruzado = sem dado daquele indicador
  naquela linha (ex: filial sem NPS): diga isso, nunca invente."""

ANALISE = """ANÁLISE (pergunta de análise, relação, padrão, tendência ou "por quê"):
- PRIMEIRO, RESPONDA À PERGUNTA, com o número que prova (calculado pelo
  código). Se ela compara ("dá mais?", "subiu?"), calcule os DOIS lados e
  diga qual é maior e quanto. Uma lista de itens soltos não é resposta.
- Depois, só as visões que ajudam (1 a 3): visão geral (total, % e
  quantos itens); concentração (quanto os primeiros somam no total);
  faixas de itens parecidos; pontos fora da curva (com o número dos dois
  lados); impacto em R$; relação entre dois indicadores (índice explicado
  em palavras: até 0,3 fraca, até 0,6 moderada, acima forte); meses que se
  repetem ao longo dos anos.
- Todo número calculado sai do CÓDIGO e o texto copia o que ele imprimiu.
  O % de um grupo é soma ÷ soma (critério do WinThor), nunca a média dos %.
- Vários critérios ("filiais que precisam de atenção..."): o corte de cada
  um é o valor do CONJUNTO impresso pelo código (ex: "desconto acima do %
  de todas juntas"; meta não atingida = abaixo de 100%; queda = variação
  negativa) — nunca um número redondo seu. Diga quantos e quais critérios
  cada item atende, do que atende mais pro que atende menos, e nunca dê a
  um item um critério que os números dele contradizem.
- Fatos sem adjetivo de julgamento ("elevado", "preocupante") e sem
  termos técnicos ("correlação", "média ponderada"). Hipóteses só no fim,
  em "**Possíveis explicações (não estão nos dados):**", no máximo 3 linhas.
- Lista cortada (ex: os 60 maiores de 2.863), mês em andamento ou falta de
  dado que importe: diga em 1 linha. Feche oferecendo aprofundar."""

COMPARACAO = """COMPARAÇÃO DE PERÍODOS:
- "{campo}_anterior", "diferenca_{campo}" e "percentual_{campo}" já vêm
  prontos: use-os pra dizer quanto cresceu/caiu (valor e %).
- Campo que já é percentual (atingimento, % de desconto): a diferença é em
  "pontos percentuais" e não cite o "percentual_" dele (seria % de %).
- Valor vazio num dos lados = aquele período não teve venda (ex: um
  domingo): diga isso e mostre o outro lado.
- Com filtros sobre o resultado, a lista JÁ tem só os itens que atendem a
  todos os critérios — não remova, não acrescente, não questione. Vazia =
  "nenhum" (e, se vier "mais_perto_do_filtro", quem chegou mais perto)."""

VARIACAO_NO_TEMPO = """VARIAÇÃO MÊS A MÊS / ANO A ANO:
- "percentual_mes_anterior" e "percentual_ano_anterior" já vêm prontos:
  cite em cada mês/ano se subiu ou caiu e quanto (ex: "Junho: 83,71, queda
  de 6,74% em relação a maio"). Vazio (1º mês/ano) = sem variação.
- Mês a mês de 2 ou mais anos: organize MÊS A MÊS, o mesmo mês dos anos lado
  a lado (nunca um ano inteiro e depois o outro)."""

COMPARACAO_ENTRE = """COMPARAÇÃO ENTRE DOIS ITENS ("comparacao_entre"):
- Use os NOMES dos dois itens (nunca "lado a/b") e, em CADA linha, o valor
  dos dois e a diferença ("a" menos "b"). Sem dado de um lado: "sem dado de
  [nome]" naquela linha. Não descreva a evolução de cada um no tempo, a não
  ser que peçam."""

TOTAIS = """TOTAIS:
- Se vier "total_de_todas_as_linhas", comece por ele e use-o EXATAMENTE —
  nunca some a lista. A quantidade de itens vem de
  "quantidade_por_dimensao" (ex: 37 lojas em 2 anos = 74 linhas — nunca
  "74 lojas")."""

ITENS_FILTRADOS = """ITEM CONSULTADO ("itens_filtrados"):
- Use o nome oficial que está ali (ex: "empresa_nome"), não o que o
  usuário digitou (ex: "mix mateus" → "Mateus Supermercados S.A., todas as
  lojas")."""

TOTAIS_POR_GRUPO = """GRUPOS ("totais_por_grupo"):
- Cite o total de cada grupo (na ordem de "totais_por_grupo") e, abaixo de
  cada um, os itens dele que vieram em "resultados"."""

FORA_DA_LISTA_DE_MENOR = """FORA DA LISTA DE "MENOR" ("fora_da_lista_de_menor"):
- Diga primeiro quantos ficaram de fora, quem são e o "motivo", e depois,
  "entre os demais", quem é o menor. Nunca chame de "o menor" quem está em
  "fora_da_lista_de_menor"."""

MES_EM_ANDAMENTO = """MÊS EM ANDAMENTO ("mes_em_andamento"):
- O resultado principal é só dos MESES FECHADOS (ex: "de janeiro a setembro
  de 2026"): diga isso e, numa frase à parte, o parcial do mês em andamento
  (de "mes_em_andamento.resultados"), deixando claro que ele não acabou."""

PERIODO_ASSUMIDO = """PERÍODO NÃO INFORMADO ("periodo_assumido"):
- É OBRIGATÓRIO dizer logo no começo que o usuário não informou o período
  (ex: "Em 2026 (você não informou o período), …") e, no fim, que dá pra
  consultar outro período."""

CODIGO_FILIAL = """CÓDIGO DE FILIAL:
- Só cite o código de uma filial se ele vier nos dados ("codigo_filial") ou
  se o usuário o informou — nunca deduza pelo nome.
- Atenção: {codigos_somados}. Perguntado um desses códigos, mostre que o
  valor é da filial somada, com os dois códigos juntos."""

RCA = """RCA:
- Consulta pelo nome do vendedor ("rcas_identificados" nos filtros): sempre
  cite nome e código (ex: "Alfredo Sousa (código 8403)"). Se também tiver uma
  filial só, termine perguntando se quer o total do RCA em todas as filiais.
- Mais de um RCA com o mesmo nome e nenhuma filial informada: o sistema
  somou todos — diga quantas filiais foram somadas e ofereça uma filial só."""

RCA_HOMONIMO = """RCAs COM O MESMO NOME ("Encontrei mais de um RCA"):
- Liste TODOS os candidatos, um por linha, no formato "nome (código NÚMERO,
  filial NOME)" — o código é o único jeito de escolher — e peça o código."""

VERIFICAR_RCA = """CONFERÊNCIA DE RCA (sem período, não traz valor):
- Encontrado: mostre nome(s) e código(s) e pergunte o período (ex: "Encontrei
  o RCA Alfredo Sousa (código 8403). Qual período você quer consultar?").
- Não encontrado: diga isso de forma natural e peça pra conferir o código —
  sem pedir período."""

META = """META DE FATURAMENTO:
- "falta_para_meta" positivo = quanto falta vender; zero ou negativo = meta
  batida (diga em quanto foi superada, nunca "falta" um valor negativo).
- "percentual_atingimento" pode passar de 100%. Meta zero = sem meta
  cadastrada (mostre só o realizado e avise).
- "necessidade_diaria" (só no mês atual): quanto vender por dia útil
  restante. Se não vier, não invente."""

META_TONELADA = """META DE TONELADA:
- Só traz a META de tonelada (não o realizado): nunca calcule atingimento
  nem "quanto falta". Responda o valor em toneladas (ex: "1.020,41
  toneladas"); o volume vendido é outra consulta."""

NPS = """NPS:
- NPS com menos de 30 respostas ("total_respostas", ou
  "total_respostas_anterior" numa comparação) é pouco confiável: diga em
  quantas respostas se baseia (ex: "100,00, com base em apenas 12
  respostas"). Com 30 ou mais, não mencione a quantidade.
- Numa comparação de NPS, cite o NPS de cada período e a diferença em
  pontos; lista vazia = nenhuma filial tinha NPS nos dois períodos."""

VENDA = """VENDA (nota):
- Identifique cada venda pela NOTA ("venda_nota"), a filial, a data e o
  cliente — o número em "venda" é interno, nunca o cite. O pedido
  ("venda_pedido") só se o usuário perguntou por ele."""

SEM_DADOS = """SEM DADOS ("encontrado": false):
- Não repita o texto técnico da "mensagem": reformule de forma natural,
  citando a filial e o período pedidos (ex: "Não há faturamento registrado
  para a filial Campos Sales em 26/08/2026."). Não invente o motivo.
- Termine dizendo o próximo passo (conferir o nome, informar o período,
  tentar outro período ou filial), conforme a mensagem."""


def regras_da_resposta(resultado: dict, nome_ferramenta: str) -> str:
    """As regras que se aplicam a ESTE resultado, juntas num texto só."""
    resultado = resultado if isinstance(resultado, dict) else {}
    texto_dos_dados = json.dumps(resultado, ensure_ascii=False, default=str)
    linhas = resultado.get("resultados") if isinstance(resultado.get("resultados"), list) else []
    primeira = linhas[0] if linhas and isinstance(linhas[0], dict) else {}
    indicadores = {resultado.get("indicador"), *(resultado.get("cruzado_com") or [])}
    agrupar_por = resultado.get("agrupar_por") or []
    filtros = resultado.get("filtros_aplicados") or {}

    secoes = [GERAIS, PERIODO, FORMATACAO]

    condicoes = [
        (LISTAS, len(linhas) > 1 or bool(resultado.get("cruzado_com"))),
        (ANALISE, len(linhas) > 2 or bool(resultado.get("cruzado_com"))),
        (COMPARACAO, "periodo_comparado" in resultado or any(k.startswith("diferenca_") for k in primeira)
         or "quantidade_antes_do_filtro" in resultado),
        (VARIACAO_NO_TEMPO, any(k in primeira for k in ("percentual_mes_anterior", "percentual_ano_anterior"))),
        (COMPARACAO_ENTRE, "comparacao_entre" in resultado),
        (TOTAIS, "total_de_todas_as_linhas" in resultado),
        (ITENS_FILTRADOS, "itens_filtrados" in resultado),
        (TOTAIS_POR_GRUPO, "totais_por_grupo" in resultado),
        (FORA_DA_LISTA_DE_MENOR, "fora_da_lista_de_menor" in resultado),
        (MES_EM_ANDAMENTO, "mes_em_andamento" in resultado),
        (PERIODO_ASSUMIDO, "periodo_assumido" in resultado),
        (CODIGO_FILIAL.format(codigos_somados=descrever_codigos_somados()),
         "filial" in agrupar_por or "filial" in filtros or "codigo_filial" in primeira),
        (RCA, "rca" in agrupar_por or "rca" in filtros or "rcas_identificados" in filtros),
        (RCA_HOMONIMO, "Encontrei mais de um RCA" in texto_dos_dados),
        (VERIFICAR_RCA, nome_ferramenta == "verificar_rca"),
        (META, "meta" in indicadores),
        (META_TONELADA, "meta_tonelada" in indicadores),
        (NPS, "nps" in indicadores),
        (VENDA, "venda" in agrupar_por or "venda" in filtros),
        (SEM_DADOS, resultado.get("encontrado") is False),
    ]

    secoes += [texto for texto, vale in condicoes if vale]
    return "\n\n".join(secoes)
