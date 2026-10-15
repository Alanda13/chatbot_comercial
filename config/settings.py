"""
Configurações do app: título da página e caminhos dos arquivos de imagem.
Caminhos absolutos (a partir da raiz do projeto), pra funcionar de
qualquer pasta de onde o Streamlit for iniciado.
"""
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent

TITULO_PAGINA = "Chatbot Comercial Ferronorte"

# Logos (assets/, fundo transparente):
# - icone_fn.png: símbolo FN em quadrado — aba do navegador, ícone das
#   respostas e da tela inicial;
# - logo_ferronorte_resumida.png: FN em cima de "Ferronorte" — topo da barra
#   lateral;
# - logo_ferronorte_completa.png: com "seu parceiro forte" — sem uso.
CAMINHO_ICONE = str(RAIZ_PROJETO / "assets" / "icone_fn.png")
CAMINHO_LOGO_SIDEBAR = str(RAIZ_PROJETO / "assets" / "logo_ferronorte_resumida.png")
