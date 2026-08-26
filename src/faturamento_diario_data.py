"""
Carregamento e preparação dos dados de Faturamento por dia,
exportados da rotina 8302 (Faturamento por RCA/Filial/Dia) do Winthor.
"""
from pathlib import Path
import pandas as pd

RAIZ_PROJETO = Path(__file__).resolve().parent.parent

ARQUIVO_8302 = (
    RAIZ_PROJETO
    / "dados"
    / "faturamento_por_rca_filial_dia_2022_a_2025.csv"
)


def carregar_faturamento_8302() -> pd.DataFrame:
    """
    Carrega o arquivo CSV exportado da rotina 8302 do Winthor,
    com o faturamento detalhado por filial, RCA, dia e forma
    de pagamento.
    """
    if not ARQUIVO_8302.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {ARQUIVO_8302}"
        )

    dados = pd.read_csv(
        ARQUIVO_8302,
        sep=";",
        encoding="latin1",
        decimal=",",
    )

    dados.columns = dados.columns.str.strip()

    # remove as colunas vazias criadas durante a exportação
    dados = dados.loc[
        :,
        ~dados.columns.str.startswith("Unnamed")
    ]

    dados["DATA"] = pd.to_datetime(
        dados["DATA"],
        dayfirst=True,
    )

    return dados
