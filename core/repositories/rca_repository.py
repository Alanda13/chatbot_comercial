"""
Cadastro dos RCAs (PCUSUARI): código → nome.

O nome do RCA vinha só das vendas (8302): quem tem meta cadastrada mas
nunca vendeu (ex: 9230, RÔMULO VIENA VERAS) ficava sem nome e a tabela
mostrava "sem dados". O cadastro cobre todos — gerado do Oracle (só
leitura) e atualizado em segundo plano por
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
        cursor.execute("SELECT CODUSUR COD_RCA, NOME FROM PCUSUARI")
        dados = pd.DataFrame(cursor.fetchall(), columns=[d[0] for d in cursor.description])
    finally:
        conexao.close()

    dados["COD_RCA"] = dados["COD_RCA"].astype("int64")
    dados["NOME"] = dados["NOME"].astype(str).str.strip()
    gravar_csv(dados, ARQUIVO_RCAS)


def carregar_nomes_do_cadastro() -> dict[int, str]:
    garantir([ARQUIVO_RCAS], atualizar, "cadastro de RCAs")
    dados = ler_csv(ARQUIVO_RCAS).dropna(subset=["NOME"])
    return dict(zip(dados["COD_RCA"].astype(int), dados["NOME"]))
