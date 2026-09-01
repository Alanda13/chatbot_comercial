"""
Carregamento dos dados de Meta de Tonelada.

Fonte: export do TARGIT (não vem do Winthor diretamente), já
reorganizado de um formato "largo" (uma coluna por RCA/mês) para um
formato normal — uma linha por filial/ano/mês/RCA. Veja
scripts/reorganizar_meta_tonelada.py para gerar esse CSV a partir do
export bruto do TARGIT.
"""
from pathlib import Path
import pandas as pd

from src.filial_utils import (
    encontrar_filial_mais_proxima,
    normalizar_nome_filial,
)

RAIZ_PROJETO = Path(__file__).resolve().parent.parent

ARQUIVO_META_TONELADA = (
    RAIZ_PROJETO
    / "dados"
    / "meta_tonelada_2024_2026.csv"
)


def carregar_meta_tonelada() -> pd.DataFrame:
    """
    Carrega o CSV de meta de tonelada (já reorganizado — veja
    scripts/reorganizar_meta_tonelada.py).
    """
    if not ARQUIVO_META_TONELADA.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {ARQUIVO_META_TONELADA}"
        )

    dados = pd.read_csv(
        ARQUIVO_META_TONELADA,
        sep=";",
    )

    dados.columns = dados.columns.str.strip()

    return dados


def resolver_nome_filial_tonelada(nome_informado: str) -> str:
    """
    Encontra o nome correto da filial na base de meta de tonelada.

    Essa base vem do TARGIT e usa o nome da razão social completa
    (ex: "COMERCIAL FERRONORTE LTDA-F09-TIMON"), diferente do formato
    mais limpo usado nas bases de faturamento (rotina 8280/8302, ex:
    "FERRONORTE TIMON") — por isso tem um resolvedor próprio.
    """
    dados = carregar_meta_tonelada()

    filiais = (
        dados["FILIAL"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )

    if not filiais:
        raise ValueError(
            "Nenhuma filial foi encontrada na base de meta de tonelada."
        )

    nome_procurado = normalizar_nome_filial(nome_informado)

    filial_encontrada = encontrar_filial_mais_proxima(
        nome_procurado,
        filiais,
    )

    if filial_encontrada is None:
        raise ValueError(
            f"A filial '{nome_informado}' não foi encontrada na base "
            "de meta de tonelada."
        )

    return filial_encontrada


def construir_lista_rca_tonelada() -> list[dict]:
    """
    Constrói uma lista de RCAs (nome e filial) presentes na base de
    meta de tonelada — usada pra resolver o nome informado pelo
    usuário. Essa base não tem código numérico de RCA (só o nome),
    diferente da base de faturamento.
    """
    dados = carregar_meta_tonelada()

    pares = dados[["RCA", "FILIAL"]].dropna().drop_duplicates()

    return [
        {
            "nome": str(linha["RCA"]).strip(),
            "filial": str(linha["FILIAL"]).strip(),
        }
        for _, linha in pares.iterrows()
    ]


def resolver_nomes_rca_tonelada(
    nome: str,
    filiais: list[str] | None = None,
) -> list[str]:
    """
    Resolve o(s) nome(s) de RCA na base de meta de tonelada, a
    partir do nome informado pelo usuário. Como essa base só tem o
    nome do vendedor (não tem código), a resolução é sempre por
    nome — mesma lógica de desambiguação usada pro RCA de
    faturamento (veja resolver_codigos_rca):
    - nome que bate com um único RCA: retorna esse nome;
    - nome que bate com vários e uma filial foi informada: usa a
      filial pra desambiguar;
    - nome que bate com vários e NENHUMA filial foi informada: soma
      todos (retorna a lista de nomes);
    - se, mesmo com a filial, sobrar mais de um: erro claro listando
      os candidatos.
    """
    rcas = construir_lista_rca_tonelada()

    nome_procurado = normalizar_nome_filial(nome)

    candidatos = [
        rca
        for rca in rcas
        if nome_procurado in normalizar_nome_filial(rca["nome"])
        or normalizar_nome_filial(rca["nome"]) in nome_procurado
    ]

    if len(candidatos) > 1 and filiais:
        candidatos_na_filial = [
            candidato
            for candidato in candidatos
            if candidato["filial"] in filiais
        ]

        if candidatos_na_filial:
            candidatos = candidatos_na_filial

    if len(candidatos) == 1:
        return [candidatos[0]["nome"]]

    if len(candidatos) > 1:
        if filiais:
            descricoes = ", ".join(
                f"{candidato['nome']} (filial {candidato['filial']})"
                for candidato in candidatos
            )
            raise ValueError(
                f"Encontrei mais de um RCA parecido com '{nome}' na "
                f"base de meta de tonelada: {descricoes}. Informe o "
                "nome completo do vendedor."
            )

        return [candidato["nome"] for candidato in candidatos]

    nome_encontrado = encontrar_filial_mais_proxima(
        nome_procurado,
        [rca["nome"] for rca in rcas],
    )

    if nome_encontrado is not None:
        return [nome_encontrado]

    raise ValueError(
        f"O RCA '{nome}' não foi encontrado na base de meta de tonelada."
    )
