"""
Configurações do app: título da página e caminhos dos arquivos de imagem.
Caminhos absolutos (a partir da raiz do projeto), pra funcionar de
qualquer pasta de onde o Streamlit for iniciado.
"""
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent

TITULO_PAGINA = "Chatbot Comercial Ferronorte"

CAMINHO_ICONE = str(RAIZ_PROJETO / "assets" / "icone_ferronorte.png")
# Letras do logo em azul — o original (logo_ferronorte.png) tem letras
# brancas, feitas pro tema escuro, e some no fundo claro.
CAMINHO_LOGO_SIDEBAR = str(RAIZ_PROJETO / "assets" / "logo_ferronorte_fundo_claro.png")
