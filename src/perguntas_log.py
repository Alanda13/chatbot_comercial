"""
Registro e consulta das perguntas feitas ao chatbot.

Usado para montar, com o tempo, um painel de perguntas mais
frequentes baseado em uso real, em vez de uma lista de exemplos
escolhida manualmente.
"""
import sqlite3
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
ARQUIVO_LOG = RAIZ_PROJETO / "dados" / "perguntas.db"


def _obter_conexao() -> sqlite3.Connection:
    ARQUIVO_LOG.parent.mkdir(parents=True, exist_ok=True)

    conexao = sqlite3.connect(ARQUIVO_LOG)
    conexao.execute(
        """
        CREATE TABLE IF NOT EXISTS perguntas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pergunta_original TEXT NOT NULL,
            pergunta_normalizada TEXT NOT NULL,
            criado_em TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    return conexao


def _normalizar_pergunta(pergunta: str) -> str:
    return " ".join(pergunta.strip().lower().split())


def registrar_pergunta(pergunta: str) -> None:
    """
    Registra uma pergunta feita ao chatbot, para fins estatísticos.
    """
    if not pergunta or not pergunta.strip():
        return

    conexao = _obter_conexao()

    try:
        conexao.execute(
            "INSERT INTO perguntas "
            "(pergunta_original, pergunta_normalizada) "
            "VALUES (?, ?)",
            (
                pergunta.strip(),
                _normalizar_pergunta(pergunta),
            ),
        )
        conexao.commit()
    finally:
        conexao.close()


def contar_perguntas_registradas() -> int:
    """
    Retorna quantas perguntas já foram registradas no total.
    """
    conexao = _obter_conexao()

    try:
        cursor = conexao.execute(
            "SELECT COUNT(*) FROM perguntas"
        )
        return cursor.fetchone()[0]
    finally:
        conexao.close()


def obter_perguntas_frequentes(limite: int = 5) -> list[dict]:
    """
    Retorna as perguntas mais frequentes já feitas ao chatbot,
    agrupadas por texto normalizado (minúsculas, sem espaços
    extras), com a quantidade de vezes que cada uma foi feita.
    """
    conexao = _obter_conexao()

    try:
        cursor = conexao.execute(
            """
            SELECT
                MIN(pergunta_original) AS exemplo,
                COUNT(*) AS quantidade
            FROM perguntas
            GROUP BY pergunta_normalizada
            ORDER BY quantidade DESC, exemplo ASC
            LIMIT ?
            """,
            (limite,),
        )
        return [
            {
                "pergunta": linha[0],
                "quantidade": linha[1],
            }
            for linha in cursor.fetchall()
        ]
    finally:
        conexao.close()
