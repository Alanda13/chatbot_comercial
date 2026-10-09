"""
Configurações do app: título da página e caminhos dos arquivos de imagem.
Caminhos absolutos (a partir da raiz do projeto), pra funcionar de
qualquer pasta de onde o Streamlit for iniciado.
"""
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent

TITULO_PAGINA = "Chatbot Comercial Ferronorte"

# Logos oficiais (assets/, fundo transparente):
# - icone_fn.png: o símbolo FN em quadrado — aba do navegador, ícone das
#   respostas e da tela inicial (o simbolo_fn.png original é 2:1 e saía achatado);
# - logo_ferronorte_resumida.png: FN em cima de "Ferronorte" — topo da barra
#   lateral (a completa, com "seu parceiro forte", ficava com a frase ilegível
#   no tamanho do topo);
# - logo_ferronorte_completa.png: FN + "Ferronorte" + "seu parceiro forte" —
#   guardada, sem uso.
CAMINHO_ICONE = str(RAIZ_PROJETO / "assets" / "icone_fn.png")
CAMINHO_LOGO_SIDEBAR = str(RAIZ_PROJETO / "assets" / "logo_ferronorte_resumida.png")
