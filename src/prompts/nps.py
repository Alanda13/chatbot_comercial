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
