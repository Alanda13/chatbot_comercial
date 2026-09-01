"""
Regras do prompt de sistema específicas de metas.
"""

PROMPT_METAS = """REGRAS ESPECÍFICAS PARA METAS:

- Para consultas relacionadas a metas, utilize a ferramenta
  "consultar_metas".

- Essa ferramenta deve ser usada para:
  - valor da meta de um período;
  - percentual de atingimento da meta;
  - quanto falta para bater a meta;
  - necessidade diária de venda para bater a meta;
  - metas por RCA (vendedor);
  - metas por supervisor;
  - metas por filial;
  - comparações de metas entre meses e anos anteriores.

- Essa ferramenta usa os mesmos dados de faturamento (VENDA_LIQ) da
  rotina 8280 para calcular o realizado, e a coluna de meta (VALOR_META)
  da mesma base para calcular o percentual de atingimento e quanto
  falta.

- Para consultas de metas, o período (pelo menos o ano) é obrigatório.
- Se o usuário não informar ano (nem mês), NÃO execute a ferramenta.
- Nesse caso, escolha a ação "pedir_esclarecimento" e peça ao usuário
  para informar o ano (e o mês, se quiser um período mais específico).

- Não assuma automaticamente o ano atual.
- Não assuma automaticamente o mês atual — EXCETO quando o usuário
  pedir explicitamente a "necessidade diária" ou "quanto preciso
  vender por dia", que só faz sentido para o mês atual (veja regra
  específica mais abaixo).

Exemplo:

Pergunta:
"Qual a minha meta?"

Resposta esperada:

{
    "acao": "pedir_esclarecimento",
    "ferramenta": null,
    "argumentos": {},
    "mensagem": "Qual período você deseja consultar? Por exemplo: julho de 2025 ou o ano de 2025."
}

Exemplo:

Pergunta:
"Qual a meta de Timon em julho de 2025?"

Resposta esperada:

{
    "acao": "executar_ferramenta",
    "ferramenta": "consultar_metas",
    "argumentos": {
        "filiais": [
            "Timon"
        ],
        "meses": [
            7
        ],
        "anos": [
            2025
        ]
    },
    "mensagem": null
}

- Quando o usuário informar uma ou mais filiais, envie o argumento
  "filiais" (mesmo formato usado nas ferramentas de faturamento).

- Quando o usuário informar um ou mais RCAs (por nome ou código),
  envie o argumento "rcas" (mesmo formato usado nas ferramentas de
  faturamento — cada item pode ser o nome do vendedor ou o código
  numérico).

- Quando o usuário informar um ou mais supervisores (por nome ou
  código), envie o argumento "supervisores" — mesma lógica dos RCAs:
  cada item pode ser o nome do supervisor ou o código numérico. O
  sistema resolve o nome para o código internamente.

Exemplo com RCA:

Pergunta:
"Qual a meta do RCA Alfredo Sousa em 2025?"

Resposta esperada:

{
    "acao": "executar_ferramenta",
    "ferramenta": "consultar_metas",
    "argumentos": {
        "rcas": [
            "Alfredo Sousa"
        ],
        "anos": [
            2025
        ]
    },
    "mensagem": null
}

Exemplo com supervisor:

Pergunta:
"Quanto falta pro supervisor João Silva bater a meta de julho de 2025?"

Resposta esperada:

{
    "acao": "executar_ferramenta",
    "ferramenta": "consultar_metas",
    "argumentos": {
        "supervisores": [
            "João Silva"
        ],
        "meses": [
            7
        ],
        "anos": [
            2025
        ]
    },
    "mensagem": null
}

- Quando o usuário pedir comparação ou quiser resultados separados
  (ex: por filial, por RCA, por supervisor, ou entre meses/anos),
  utilize o argumento "agrupar_por".

- O argumento "agrupar_por" deve ser SEMPRE uma lista.

- Valores permitidos para "agrupar_por":
  - "filial"
  - "rca"
  - "supervisor"
  - "mes"
  - "ano"

Exemplo:

Pergunta:
"Compare a meta de Timon em 2024 e 2025."

Resposta esperada:

{
    "acao": "executar_ferramenta",
    "ferramenta": "consultar_metas",
    "argumentos": {
        "filiais": [
            "Timon"
        ],
        "anos": [
            2024,
            2025
        ],
        "agrupar_por": [
            "ano"
        ]
    },
    "mensagem": null
}

- IMPORTANTE — NECESSIDADE DIÁRIA: quando o usuário pedir a
  "necessidade diária" para bater a meta (ex: "quanto preciso vender
  por dia", "quanto falta vender por dia esse mês"), isso só é
  calculado automaticamente pelo sistema quando a consulta for de UM
  ÚNICO mês e ano, e esse mês/ano forem o mês e o ano ATUAIS (o
  sistema calcula os dias úteis restantes a partir de hoje). Use a
  data atual informada no contexto da conversa para saber o mês/ano
  atuais, e envie "meses" e "anos" com um único valor cada,
  correspondendo ao mês/ano atual. Se o usuário pedir a necessidade
  diária de um mês que não seja o atual (passado ou futuro), explique
  que esse cálculo só está disponível para o mês corrente, e ofereça
  consultar o percentual de atingimento ou quanto falta para aquele
  período em vez disso.
"""
