"""
Carregamento e preparação dos dados de Faturamento
exportados da rotina 8280 (Faturamento por RCA/Filial/Mes/Ano) do Winthor.
"""
from pathlib import Path
import pandas as pd

from src.filiais import padronizar_filiais

RAIZ_PROJETO = Path(__file__).resolve().parent.parent

ARQUIVO_8280 = (
    RAIZ_PROJETO
    /"dados"
    /"faturamento_mensal.csv"
)
def carregar_faturamento_8280() -> pd.DataFrame:
    """
    Carregar o arquivo CSV exportado da rotina 8280 do Winthor
    """
    if not ARQUIVO_8280.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {ARQUIVO_8280}"
        )
    dados = pd.read_csv(
        ARQUIVO_8280,
        sep=";",
        encoding="latin1",
        decimal=",",
    )
    #removendo as colunas vazias criadas durante a execução
    dados = dados.loc [
        :,
        ~dados.columns.str.startswith("Unnamed")
    ]
    return padronizar_filiais(dados, dados["CODFILIAL"])
