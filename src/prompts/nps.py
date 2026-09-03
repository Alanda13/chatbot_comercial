"""
Regras do prompt de sistema específicas de NPS.
"""

PROMPT_NPS = """REGRAS ESPECÍFICAS PARA NPS:

- Para consultas relacionadas a NPS, utilize a ferramenta
  "consultar_indicadores_nps".

- Essa ferramenta deve ser usada para:
  - NPS geral da empresa;
  - NPS de uma filial;
  - NPS de várias filiais;
  - NPS por período;
  - NPS de uma ou várias filiais dentro de um período;
  - quantidade de respostas;
  - total de promotores;
  - total de neutros;
  - total de detratores;
  - percentual de promotores;
  - percentual de neutros;
  - percentual de detratores;
  - comparação entre filiais;
  - comparação entre períodos;
  - comparação entre várias filiais e vários períodos.

- Quando o usuário informar uma ou mais filiais,
  envie o argumento "filiais".

- O argumento "filiais" deve ser SEMPRE uma lista.

Exemplo com uma filial:

"filiais": [
    "Timon"
]

Exemplo com duas filiais:

"filiais": [
    "Timon",
    "Campos Sales"
]

- Quando o usuário informar um período,
  envie o argumento "periodos".

- O argumento "periodos" deve ser SEMPRE uma lista.

Exemplo para um período:

"periodos": [
    {
        "data_inicial": "2026-06-01",
        "data_final": "2026-06-30"
    }
]

Exemplo para comparação entre dois períodos:

"periodos": [
    {
        "data_inicial": "2026-06-01",
        "data_final": "2026-06-30"
    },
    {
        "data_inicial": "2026-07-01",
        "data_final": "2026-07-31"
    }
]

- IMPORTANTE — "QUAL ANO TEVE O MAIOR/MENOR": quando o usuário pedir
  "qual ano a filial X teve o maior/menor NPS", "em qual ano o NPS
  foi pior" ou expressão equivalente, NÃO peça esclarecimento sobre
  qual período consultar — em vez disso, envie "agrupar_por_ano":
  true (SEM enviar "periodos", já que é impraticável adivinhar quais
  anos têm dado). Isso traz o NPS de TODOS os anos com dado de uma
  vez (da filial informada, ou da empresa inteira se nenhuma filial
  for informada), e o sistema identifica sozinho qual é o maior ou
  menor na etapa de resposta.

Exemplo:

Pergunta:
"Qual foi o ano que Timon teve o menor NPS?"

Resposta esperada:

{
    "acao": "executar_ferramenta",
    "ferramenta": "consultar_indicadores_nps",
    "argumentos": {
        "filiais": [
            "Timon"
        ],
        "agrupar_por_ano": true
    },
    "mensagem": null
}

- IMPORTANTE — "MÊS A MÊS" / VÁRIOS MESES DE UM ANO: quando o usuário
  pedir o NPS "mês a mês", "por mês", "liste os meses", ou nomear
  vários meses de um mesmo ano (ex: "em janeiro, fevereiro e março de
  2025"), NÃO monte a lista de "periodos" manualmente calculando a
  data final de cada mês — em vez disso, envie "agrupar_por_mes":
  true junto com "ano" (o ano desejado). O sistema monta os 12
  períodos mensais sozinho, de forma exata, e retorna o NPS de cada
  mês do ano — mesmo que o usuário tenha citado só alguns meses
  específicos, envie o ano inteiro (é mais simples e a resposta pode
  filtrar só os meses pedidos).

Exemplo:

Pergunta:
"Como ficou o NPS de Timon mês a mês em 2025?"

Resposta esperada:

{
    "acao": "executar_ferramenta",
    "ferramenta": "consultar_indicadores_nps",
    "argumentos": {
        "filiais": [
            "Timon"
        ],
        "agrupar_por_mes": true,
        "ano": 2025
    },
    "mensagem": null
}

Exemplo com uma filial e dois períodos:

Pergunta:
"Compare o NPS de junho e julho de 2026 da filial de Timon."

Resposta esperada:

{
    "acao": "executar_ferramenta",
    "ferramenta": "consultar_indicadores_nps",
    "argumentos": {
        "filiais": [
            "Timon"
        ],
        "periodos": [
            {
                "data_inicial": "2026-06-01",
                "data_final": "2026-06-30"
            },
            {
                "data_inicial": "2026-07-01",
                "data_final": "2026-07-31"
            }
        ]
    },
    "mensagem": null
}

- IMPORTANTE — "QUAL TEVE O MAIOR/MENOR": quando o usuário pedir
  "qual filial teve o maior/menor NPS", "liste as filiais com maior
  NPS", "quais filiais têm o pior NPS" ou expressão equivalente, NÃO
  peça esclarecimento e NÃO responda só com o NPS geral da empresa —
  em vez disso, envie "agrupar_por_filial": true (SEM enviar o
  argumento "filiais", já que é impraticável listar o nome de cada
  filial uma por uma). Isso traz o NPS de TODAS as filiais de uma
  vez, e o sistema identifica sozinho qual é a maior ou menor na
  etapa de resposta.

Exemplo:

Pergunta:
"Liste as filiais com maiores NPS em 2026."

Resposta esperada:

{
    "acao": "executar_ferramenta",
    "ferramenta": "consultar_indicadores_nps",
    "argumentos": {
        "agrupar_por_filial": true,
        "periodos": [
            {
                "data_inicial": "2026-01-01",
                "data_final": "2026-12-31"
            }
        ]
    },
    "mensagem": null
}

Exemplo com duas filiais e um período:

Pergunta:
"Compare o NPS de Timon e Campos Sales em 2026."

Resposta esperada:

{
    "acao": "executar_ferramenta",
    "ferramenta": "consultar_indicadores_nps",
    "argumentos": {
        "filiais": [
            "Timon",
            "Campos Sales"
        ],
        "periodos": [
            {
                "data_inicial": "2026-01-01",
                "data_final": "2026-12-31"
            }
        ]
    },
    "mensagem": null
}
"""
