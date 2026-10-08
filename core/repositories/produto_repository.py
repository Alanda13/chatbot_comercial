"""
Carregamento dos dados de desconto por produto (e por grupo e família).

Dois CSVs, gerados do Oracle e atualizados em segundo plano por
`core/services/atualizador_service.py` (mesma regra dos outros):

- `desconto_produto.csv`: desconto e faturamento de tabela por
  filial/ano/mês/produto, desde 2020 (~1 milhão de linhas). Sem RCA
  (decisão de 07/10/2026, pra ficar leve). Mesma conta do desconto mensal
  (igual à rotina 8302).
- `produtos.csv`: código, descrição, GRUPO e FAMÍLIA de cada produto.

GRUPO e FAMÍLIA não existem no Oracle: vêm da planilha BASE_PRODUTOS,
mantida por um gerente na pasta da rede (o "grupo" é a coluna
GRUPO_OU_KPI — confirmado pela supervisora). A planilha é copiada pra
`dados/` quando muda; se a rede estiver fora, vale a última cópia.
Produto que não está na planilha (cadastro novo) fica "SEM GRUPO" — nunca
some dos totais.
"""
import re
import shutil
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd

from core.repositories.arquivos_repository import (
    antes_da_janela_mensal,
    garantir,
    gravar_csv,
    inicio_da_janela_parcial,
    ler_csv,
)
from core.repositories.oracle import get_connection
from core.repositories.faturamento_repository import (
    ANO_INICIO_PADRAO,
    RAIZ_PROJETO,
    _FILTRO_VENDA_VALIDA,
    juntar_devolucao,
)
from core.repositories.filiais_repository import padronizar_filiais
from core.logger import obter_logger

logger = obter_logger(__name__)

ARQUIVO_DESCONTO_PRODUTO = RAIZ_PROJETO / "dados" / "desconto_produto.csv"
ARQUIVO_PRODUTOS = RAIZ_PROJETO / "dados" / "produtos.csv"

# Endereço da rede (não a letra "E:", que pode não existir no servidor).
PASTA_PLANILHA = Path(
    r"\\10.0.1.213\0002 - comercial\1 - REUNIÕES\1.1 - REUNIÃO SEMANAL\BASE_PRODUTOS"
)
COPIA_PLANILHA = RAIZ_PROJETO / "dados" / "base_produtos.xlsx"

SEM_GRUPO = "SEM GRUPO"

COLUNAS_DESCONTO = ["CODFILIAL", "ANO", "MES", "CODPROD", "VALORDESC", "VENDA_TABELA", "VENDA_BRUTA",
    "VALOR_DEV", "VENDA_LIQ",
]
COLUNAS_PRODUTOS = ["CODPROD", "PRODUTO", "GRUPO", "FAMILIA"]


def _consultar_desconto(cursor, desde: date) -> pd.DataFrame:
    cursor.arraysize = 10000
    cursor.execute(
        f"""
        SELECT CODFILIAL, EXTRACT(YEAR FROM DTSAIDA) ANO,
               EXTRACT(MONTH FROM DTSAIDA) MES, CODPROD,
               ROUND(SUM(VLDESCONTO * QT), 4) VALORDESC,
               ROUND(SUM(VLTABELA), 2) VENDA_TABELA,
               ROUND(SUM(VLVENDA), 2) VENDA_BRUTA
        FROM VIEW_VENDAS_RESUMO_FATURAMENTO
        WHERE DTSAIDA >= :desde
        {_FILTRO_VENDA_VALIDA}
        GROUP BY CODFILIAL, EXTRACT(YEAR FROM DTSAIDA),
                 EXTRACT(MONTH FROM DTSAIDA), CODPROD
        """,
        desde=desde,
    )
    colunas = [d[0] for d in cursor.description]
    return pd.DataFrame(cursor.fetchall(), columns=colunas)


def _consultar_cadastro(cursor) -> pd.DataFrame:
    cursor.arraysize = 10000
    cursor.execute("SELECT CODPROD, TRIM(DESCRICAO) PRODUTO FROM PCPRODUT")
    colunas = [d[0] for d in cursor.description]
    return pd.DataFrame(cursor.fetchall(), columns=colunas)


def atualizar_copia_da_planilha() -> Path:
    """
    Copia a planilha da rede pra `dados/` quando ela é mais nova que a
    cópia. Procura qualquer BASE_PRODUTOS*.xlsx (o nome hoje tem um "(1)"
    que pode mudar) e ignora o arquivo de trava do Excel ("~$...").
    Sem rede, segue com a cópia que já existe.
    """
    try:
        planilhas = sorted(
            (p for p in PASTA_PLANILHA.glob("BASE_PRODUTOS*.xlsx") if not p.name.startswith("~$")),
            key=lambda p: p.stat().st_mtime,
        )
    except OSError as erro:
        planilhas = []
        logger.warning(f"Pasta da planilha de produtos inacessível: {erro}")

    if planilhas:
        original = planilhas[-1]
        if not COPIA_PLANILHA.exists() or original.stat().st_mtime > COPIA_PLANILHA.stat().st_mtime:
            COPIA_PLANILHA.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, COPIA_PLANILHA)
            logger.info(f"Planilha de produtos atualizada a partir de {original.name}")

    if not COPIA_PLANILHA.exists():
        raise FileNotFoundError(
            f"Planilha de produtos não encontrada em {PASTA_PLANILHA} nem cópia em {COPIA_PLANILHA}"
        )

    return COPIA_PLANILHA


def _classificacao() -> pd.DataFrame:
    planilha = pd.read_excel(
        atualizar_copia_da_planilha(), sheet_name="Bases_Produto",
        usecols=["CODPROD", "GRUPO_OU_KPI", "FAMILIA"],
    )
    planilha = planilha.dropna(subset=["CODPROD"]).drop_duplicates("CODPROD")
    planilha["CODPROD"] = planilha["CODPROD"].astype(int)
    return planilha.rename(columns={"GRUPO_OU_KPI": "GRUPO"})


def _montar_produtos(cadastro: pd.DataFrame, desconto: pd.DataFrame) -> pd.DataFrame:
    """Cadastro de quem aparece no desconto, com GRUPO e FAMÍLIA da planilha."""
    produtos = cadastro[cadastro["CODPROD"].isin(desconto["CODPROD"])].copy()
    produtos["CODPROD"] = produtos["CODPROD"].astype(int)
    produtos = produtos.merge(_classificacao(), on="CODPROD", how="left")
    produtos["GRUPO"] = produtos["GRUPO"].fillna(SEM_GRUPO).astype(str).str.strip()
    # Sem família na planilha: o próprio produto é a família dele.
    produtos["FAMILIA"] = (
        produtos["FAMILIA"].where(produtos["FAMILIA"].notna(), produtos["PRODUTO"])
        .astype(str).str.strip()
    )
    return produtos[COLUNAS_PRODUTOS]


def _buscar(desde: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    conexao = get_connection()

    try:
        cursor = conexao.cursor()
        desconto = juntar_devolucao(
            _consultar_desconto(cursor, desde), cursor, desde, {"CODPROD": "CODPROD"}
        )
        cadastro = _consultar_cadastro(cursor)
    finally:
        conexao.close()

    desconto["CODPROD"] = desconto["CODPROD"].astype(int)

    return desconto[COLUNAS_DESCONTO], cadastro


def atualizar(completa: bool) -> None:
    """
    Completa: tudo desde 2020. Parcial: só o mês atual e o anterior,
    juntando com os meses mais antigos do CSV. A classificação (grupo e
    família) é refeita sempre — pega a planilha nova do gerente.
    """
    if completa or not (ARQUIVO_DESCONTO_PRODUTO.exists() and ARQUIVO_PRODUTOS.exists()):
        desconto, cadastro = _buscar(date(ANO_INICIO_PADRAO, 1, 1))
    else:
        desde = inicio_da_janela_parcial()
        antigo = antes_da_janela_mensal(ler_csv(ARQUIVO_DESCONTO_PRODUTO), desde)
        novo, cadastro = _buscar(desde)
        desconto = pd.concat([antigo, novo], ignore_index=True)

    gravar_csv(_montar_produtos(cadastro, desconto), ARQUIVO_PRODUTOS)
    gravar_csv(desconto, ARQUIVO_DESCONTO_PRODUTO)


def _garantir() -> None:
    garantir(
        [ARQUIVO_DESCONTO_PRODUTO, ARQUIVO_PRODUTOS], atualizar, "desconto por produto"
    )


def carregar_produtos() -> pd.DataFrame:
    _garantir()
    return ler_csv(ARQUIVO_PRODUTOS, dtype={"GRUPO": str, "FAMILIA": str, "PRODUTO": str})


def carregar_desconto_produto() -> pd.DataFrame:
    """Desconto por filial/mês/produto, com descrição, grupo e família."""
    _garantir()
    dados = ler_csv(ARQUIVO_DESCONTO_PRODUTO)
    dados = dados.merge(carregar_produtos(), on="CODPROD", how="left")
    dados["GRUPO"] = dados["GRUPO"].fillna(SEM_GRUPO)
    return padronizar_filiais(dados, dados["CODFILIAL"])


# --- busca pelo nome ou código ---------------------------------------------

_MAX_OPCOES = 10


def _normalizar(texto) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or "").upper())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", texto).split())


def _contem(serie: pd.Series, procurado: str) -> pd.Series:
    """Todas as palavras procuradas aparecem no nome (em qualquer ordem)."""
    normalizados = serie.map(_normalizar)
    palavras = _normalizar(procurado).split()
    achou = pd.Series(True, index=serie.index)
    for palavra in palavras:
        achou &= normalizados.str.contains(palavra, regex=False)
    return achou


def _opcoes(valores: list[str]) -> str:
    texto = "; ".join(valores[:_MAX_OPCOES])
    if len(valores) > _MAX_OPCOES:
        texto += f"; e mais {len(valores) - _MAX_OPCOES}"
    return texto


def _resolver_nome(valor, coluna: str, descricao: str) -> list[str]:
    """Grupo ou família pelo nome: igual → ele; um só parecido → ele; vários → pergunta."""
    nomes = pd.Series(carregar_produtos()[coluna].dropna().unique())
    procurado = _normalizar(valor)
    iguais = [nome for nome in nomes if _normalizar(nome) == procurado]

    if iguais:
        return iguais[:1]

    achados = sorted(nomes[_contem(nomes, valor)])

    if len(achados) == 1:
        return achados

    if not achados:
        raise ValueError(f"Não encontrei {descricao} '{valor}'.")

    raise ValueError(
        f"Encontrei mais de um(a) {descricao} com '{valor}': {_opcoes(achados)}. "
        "Mostre as opções ao usuário e pergunte qual (ou quais) ele quer."
    )


def resolver_grupos(valor, filiais=None) -> list[str]:
    return _resolver_nome(valor, "GRUPO", "grupo")


def resolver_familias(valor, filiais=None) -> list[str]:
    return _resolver_nome(valor, "FAMILIA", "família")


def resolver_produtos(valor, filiais=None) -> list[int]:
    """
    Código → aquele produto. Nome → os produtos com aquelas palavras; se
    forem todos da MESMA família, a família inteira (ex: "vergalhão 10" →
    família "VERGALHÃO 10,0"); se forem de famílias diferentes, pergunta
    qual família.
    """
    produtos = carregar_produtos()
    texto = str(valor).strip()

    if texto.isdigit():
        codigo = int(texto)
        if codigo not in set(produtos["CODPROD"]):
            raise ValueError(f"O produto de código {codigo} não teve venda desde 2020.")
        return [codigo]

    achados = produtos[_contem(produtos["PRODUTO"], texto)]

    if achados.empty:
        raise ValueError(f"Não encontrei o produto '{texto}'.")

    familias = sorted(achados["FAMILIA"].unique())

    # Se só uma das famílias tem as palavras no PRÓPRIO nome, é ela ("vergalhão
    # 10" → "VERGALHÃO 10,0", e não "BARRA REDONDA A36 3/8", que só tem um
    # produto com "vergalhão" na descrição).
    pelo_nome = [familia for familia in familias if _contem(pd.Series([familia]), texto).iloc[0]]

    if len(pelo_nome) == 1:
        familias = pelo_nome

    if len(familias) > 1:
        raise ValueError(
            f"'{texto}' aparece em mais de uma família de produtos: {_opcoes(familias)}. "
            "Mostre as famílias ao usuário e pergunte qual (ou quais) ele quer — "
            "depois consulte pelo filtro 'familia'."
        )

    return produtos.loc[produtos["FAMILIA"] == familias[0], "CODPROD"].tolist()
