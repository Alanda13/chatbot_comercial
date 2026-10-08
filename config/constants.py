"""
Valores fixos do app: cores da marca, nomes dos meses e as sugestões de
pergunta da tela inicial.
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

# Sugestões da tela inicial (como as do ChatGPT): uma por assunto. O
# clique faz a pergunta de verdade — a resposta vem sempre atualizada.
SUGESTOES = [
    {"rotulo": "💰 Faturamento de Timon em julho de 2025",
     "pergunta": "Qual foi o faturamento de Timon em julho de 2025?"},
    {"rotulo": "🎯 Meta e atingimento das filiais no mês passado",
     "pergunta": "Qual o atingimento da meta de cada filial no mês passado?"},
    {"rotulo": "🏷️ Grupos de produtos com mais desconto",
     "pergunta": "Quais os 5 grupos de produtos com mais desconto este ano?"},
    {"rotulo": "⭐ NPS do mês passado",
     "pergunta": "Qual o NPS do mês passado?"},
]
