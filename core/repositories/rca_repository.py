"""
Cadastro dos RCAs (PCUSUARI): código → nome, supervisor e filial.

Cobre também quem tem meta cadastrada mas nunca vendeu. Gerado do Oracle
(só leitura) e atualizado em segundo plano por
`core/services/atualizador_service.py`, como os outros CSVs.
"""
import pandas as pd

from core.repositories.arquivos_repository import garantir, gravar_csv, ler_csv
from core.repositories.faturamento_repository import RAIZ_PROJETO

ARQUIVO_RCAS = RAIZ_PROJETO / "data" / "rcas.csv"


def atualizar(completa: bool) -> None:
    """O cadastro é pequeno: sempre lido inteiro (completa ou não)."""
    from core.repositories.oracle import get_connection

    conexao = get_connection()

    try:
        cursor = conexao.cursor()
        cursor.execute(
            "SELECT CODUSUR COD_RCA, NOME, CODSUPERVISOR COD_SUPERVISOR, CODFILIAL FROM PCUSUARI"
        )
        dados = pd.DataFrame(cursor.fetchall(), columns=[d[0] for d in cursor.description])
    finally:
        conexao.close()

    dados["COD_RCA"] = dados["COD_RCA"].astype("int64")
    dados["NOME"] = dados["NOME"].astype(str).str.strip()
    # A filial é texto no Oracle (tem "99" e vazio).
    dados["CODFILIAL"] = pd.to_numeric(dados["CODFILIAL"], errors="coerce")
    gravar_csv(dados, ARQUIVO_RCAS)


def carregar_cadastro() -> pd.DataFrame:
    garantir([ARQUIVO_RCAS], atualizar, "cadastro de RCAs")
    return ler_csv(ARQUIVO_RCAS)


def carregar_nomes_do_cadastro() -> dict[int, str]:
    dados = carregar_cadastro().dropna(subset=["NOME"])
    return dict(zip(dados["COD_RCA"].astype(int), dados["NOME"]))
