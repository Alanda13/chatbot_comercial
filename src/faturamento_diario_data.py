"""
Carregamento e preparação dos dados de Faturamento por dia,
exportados da rotina 8302 (Faturamento por RCA/Filial/Dia) do Winthor.
"""
from pathlib import Path
import pandas as pd

from src.filial_utils import (
    encontrar_filial_mais_proxima,
    normalizar_nome_filial,
)

RAIZ_PROJETO = Path(__file__).resolve().parent.parent

ARQUIVO_8302 = (
    RAIZ_PROJETO
    / "dados"
    / "faturamento_por_rca_filial_dia_2020_a_2025.csv"
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

    # removendo as colunas vazias criadas durante a exportação
    dados = dados.loc[
        :,
        ~dados.columns.str.startswith("Unnamed")
    ]

    dados["DATA"] = pd.to_datetime(
        dados["DATA"],
        dayfirst=True,
    )

    return dados


def construir_mapa_rca_nome() -> dict[int, str]:
    """
    Constrói um mapa de código do RCA para o nome do vendedor.

    A rotina 8302 é a única fonte que traz o nome do RCA (coluna
    NOME_RCA) — a 8280 só tem o código. Quando o mesmo código
    aparece com nomes diferentes ao longo do tempo, fica o primeiro
    nome encontrado.
    """
    dados = carregar_faturamento_8302()

    pares = (
        dados[["COD_RCA", "NOME_RCA"]]
        .dropna()
        .drop_duplicates(subset="COD_RCA")
    )

    return {
        int(codigo): str(nome).strip()
        for codigo, nome in zip(
            pares["COD_RCA"],
            pares["NOME_RCA"],
        )
    }


def resolver_codigo_rca(nome_ou_codigo: str | int) -> int:
    """
    Resolve o código numérico de um RCA a partir do que o usuário
    informou — o próprio código, ou o nome do vendedor (a IA nem
    sempre sabe o código, então precisa poder buscar por nome).
    """
    if isinstance(nome_ou_codigo, int):
        return nome_ou_codigo

    texto = str(nome_ou_codigo).strip()

    if texto.isdigit():
        return int(texto)

    mapa_rca_nome = construir_mapa_rca_nome()

    nome_procurado = normalizar_nome_filial(texto)

    nome_encontrado = encontrar_filial_mais_proxima(
        nome_procurado,
        list(mapa_rca_nome.values()),
    )

    if nome_encontrado is not None:
        for codigo, nome in mapa_rca_nome.items():
            if nome == nome_encontrado:
                return codigo

    raise ValueError(
        f"O RCA '{nome_ou_codigo}' não foi encontrado."
    )
