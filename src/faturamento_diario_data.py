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

ARQUIVO_8302_COBRANCA = (
    RAIZ_PROJETO
    / "dados"
    / "rotina 8302 2024 a 2025 cobranca.csv"
)


def _carregar_csv_8302(caminho: Path) -> pd.DataFrame:
    if not caminho.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {caminho}"
        )

    dados = pd.read_csv(
        caminho,
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


def carregar_faturamento_8302() -> pd.DataFrame:
    """
    Carrega o arquivo CSV exportado da rotina 8302 do Winthor,
    com o faturamento detalhado por filial, RCA, dia e forma
    de pagamento.
    """
    return _carregar_csv_8302(ARQUIVO_8302)


def carregar_faturamento_8302_cobranca() -> pd.DataFrame:
    """
    Carrega um export separado da rotina 8302 (2024-2025), usado
    SOMENTE para agrupamento por forma de pagamento — o arquivo
    principal (ARQUIVO_8302) tem a coluna COBRANCA sempre vazia,
    então essa consulta específica usa essa base alternativa, mais
    recente e com a forma de pagamento preenchida. Cobre um período
    menor que o arquivo principal, então não substitui ele nas
    outras consultas.
    """
    return _carregar_csv_8302(ARQUIVO_8302_COBRANCA)


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


def construir_lista_rca() -> list[dict]:
    """
    Constrói uma lista de RCAs com código, nome e filial — usada
    para mostrar candidatos de forma legível quando um nome de RCA
    for ambíguo (o mesmo vendedor pode ter um código diferente em
    cada filial).
    """
    dados = carregar_faturamento_8302()

    pares = (
        dados[["COD_RCA", "NOME_RCA", "FILIAL"]]
        .dropna(subset=["COD_RCA", "NOME_RCA"])
        .drop_duplicates(subset="COD_RCA")
    )

    return [
        {
            "codigo": int(linha["COD_RCA"]),
            "nome": str(linha["NOME_RCA"]).strip(),
            "filial": str(linha["FILIAL"]).strip(),
        }
        for _, linha in pares.iterrows()
    ]


def resolver_codigos_rca(
    nome_ou_codigo: str | int,
    filiais: list[str] | None = None,
) -> list[int]:
    """
    Resolve o(s) código(s) numérico(s) de RCA a partir do que o
    usuário informou — o próprio código, ou o nome do vendedor (a IA
    nem sempre sabe o código, então precisa poder buscar por nome).

    Como existem muitos vendedores, o mesmo nome pode bater com mais
    de um RCA (ex: "André Alves" existe com um código diferente em
    cada filial em que atua):
    - se uma filial foi informada na pergunta, ela é usada pra
      restringir os candidatos automaticamente — é o caso mais
      comum de quem usa o chatbot (gerente perguntando pelo RCA da
      própria loja);
    - se, mesmo assim, sobrar mais de um candidato, uma exceção
      clara é levantada, listando código e filial de cada um, em vez
      de escolher um deles silenciosamente;
    - se NENHUMA filial foi informada, todos os códigos encontrados
      para aquele nome são retornados juntos, para que a consulta
      some o faturamento total desse RCA em todas as filiais em que
      ele aparece — é o comportamento esperado quando o usuário não
      restringe a busca a uma loja específica.

    Quando o código já vem numérico (informado direto pelo usuário,
    ou já resolvido antes), ele é validado contra a base — um código
    inexistente levanta erro imediatamente, em vez de seguir adiante
    e só descobrir lá na frente, quando a consulta não retornar
    nenhum dado, o que faria parecer um problema de período.
    """
    rcas = construir_lista_rca()

    texto = str(nome_ou_codigo).strip()

    if isinstance(nome_ou_codigo, int) or texto.isdigit():
        codigo = (
            nome_ou_codigo
            if isinstance(nome_ou_codigo, int)
            else int(texto)
        )

        if not any(rca["codigo"] == codigo for rca in rcas):
            raise ValueError(
                f"O RCA de código {codigo} não foi encontrado."
            )

        return [codigo]

    nome_procurado = normalizar_nome_filial(texto)

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
        return [candidatos[0]["codigo"]]

    if len(candidatos) > 1:
        if filiais:
            descricoes = ", ".join(
                f"{candidato['nome']} (código {candidato['codigo']}, "
                f"filial {candidato['filial']})"
                for candidato in candidatos
            )
            raise ValueError(
                f"Encontrei mais de um RCA parecido com "
                f"'{nome_ou_codigo}': {descricoes}. Informe o código "
                "do RCA que deseja consultar."
            )

        # Nenhuma filial foi informada: soma o faturamento de todos
        # os RCAs encontrados com esse nome.
        return [candidato["codigo"] for candidato in candidatos]

    # Nenhuma correspondência direta por substring: tenta por
    # similaridade textual, para tolerar pequenos erros de digitação.
    nome_encontrado = encontrar_filial_mais_proxima(
        nome_procurado,
        [rca["nome"] for rca in rcas],
    )

    if nome_encontrado is not None:
        for rca in rcas:
            if rca["nome"] == nome_encontrado:
                return [rca["codigo"]]

    raise ValueError(
        f"O RCA '{nome_ou_codigo}' não foi encontrado."
    )


def verificar_rca(
    nome_ou_codigo: str | int,
    filiais: list[str] | None = None,
) -> dict:
    """
    Verifica se um RCA (por nome ou código) existe, sem precisar de
    período — usada pra confirmar o RCA antes de pedir o período ao
    usuário, evitando pedir uma informação desnecessária quando o
    RCA nem existe na base.
    """
    try:
        codigos = resolver_codigos_rca(nome_ou_codigo, filiais=filiais)
    except ValueError as error:
        return {
            "encontrado": False,
            "mensagem": str(error),
        }

    mapa_rca_nome = construir_mapa_rca_nome()

    return {
        "encontrado": True,
        "rcas_identificados": [
            f"{mapa_rca_nome.get(codigo, 'nome não identificado')} "
            f"(código {codigo})"
            for codigo in codigos
        ],
    }
