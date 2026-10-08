"""
Valores fixos do app: cores da marca, nomes dos meses e as perguntas de
exemplo da barra lateral.
"""

# Cores da marca Ferronorte, usadas nos acentos visuais do app.
AZUL_FERRONORTE = "#0E5EA6"
LARANJA_FERRONORTE = "#F18325"
VERDE_FERRONORTE = "#349959"

MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}

# Perguntas norteadoras: uma por indicador, já mostrando a resposta,
# pra dar uma ideia rápida do que o chatbot responde.
#
# "resposta" fixa só é usada para períodos FECHADOS (já aconteceram e
# não mudam mais) de indicadores que vêm de base histórica (CSV) —
# faturamento e meta. Quando "resposta" é None, o clique busca o dado
# ao vivo (mesmo fluxo de uma pergunta digitada), porque o indicador é
# ligado ao banco e muda a cada consulta.
PERGUNTAS_NORTEADORAS = [
    {
        "categoria": "💰 Faturamento",
        "pergunta": "Qual foi o faturamento de Timon em julho de 2025?",
        "resposta": (
            "O faturamento da filial Timon em julho de 2025 foi de "
            "R$ 10.610.613,36."
        ),
    },
    {
        "categoria": "🎯 Meta de faturamento",
        "pergunta": "Qual a meta de Timon em julho de 2025?",
        "resposta": (
            "A meta de faturamento da filial Timon em julho de 2025 "
            "foi de R$ 8.671.193,51."
        ),
    },
    {
        "categoria": "🎯 Meta de tonelada",
        "pergunta": "Qual a meta de tonelada de Timon em 2025?",
        "resposta": (
            "A meta de tonelada da filial Timon em 2025 é de "
            "11.462,34 toneladas."
        ),
    },
    {
        "categoria": "⭐ NPS",
        "pergunta": "Qual o NPS do mês passado?",
        "resposta": "O NPS do mês passado (agosto de 2026) foi de 90,74.",
    },
]
