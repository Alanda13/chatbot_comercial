"""
Utilitários de apoio para o indicador de Metas.

A própria rotina 8280 (Faturamento por RCA/Filial/Mês/Ano) já traz
VALOR_META, PERC_META, COD_SUPERVISOR e NOME_SUPERVISOR por linha —
não é preciso nenhuma base nova.
"""
from src.faturamento_data import carregar_faturamento_8280
from src.filial_utils import (
    encontrar_filial_mais_proxima,
    normalizar_nome_filial,
)


def construir_lista_supervisores() -> list[dict]:
    """
    Constrói uma lista de supervisores com código, nome e filial —
    usada para resolver o nome informado pelo usuário e mostrar
    candidatos legíveis quando houver ambiguidade.
    """
    dados = carregar_faturamento_8280()

    pares = (
        dados[["COD_SUPERVISOR", "NOME_SUPERVISOR", "FILIAL"]]
        .dropna(subset=["COD_SUPERVISOR", "NOME_SUPERVISOR"])
        .drop_duplicates(subset="COD_SUPERVISOR")
    )

    return [
        {
            "codigo": int(linha["COD_SUPERVISOR"]),
            "nome": str(linha["NOME_SUPERVISOR"]).strip(),
            "filial": str(linha["FILIAL"]).strip(),
        }
        for _, linha in pares.iterrows()
    ]


def resolver_codigos_supervisor(
    nome_ou_codigo: str | int,
    filiais: list[str] | None = None,
) -> list[int]:
    """
    Resolve o(s) código(s) numérico(s) de supervisor a partir do
    nome ou código informado — mesma lógica usada para RCA (veja
    resolver_codigos_rca em faturamento_diario_data.py):
    - código numérico: validado contra a base;
    - nome que bate com um único supervisor: retorna esse código;
    - nome que bate com vários e uma filial foi informada: usa a
      filial pra desambiguar;
    - nome que bate com vários e NENHUMA filial foi informada: soma
      todos os códigos encontrados;
    - se, mesmo com a filial, sobrar mais de um: erro claro listando
      cada candidato.
    """
    supervisores = construir_lista_supervisores()

    texto = str(nome_ou_codigo).strip()

    if isinstance(nome_ou_codigo, int) or texto.isdigit():
        codigo = (
            nome_ou_codigo
            if isinstance(nome_ou_codigo, int)
            else int(texto)
        )

        if not any(sup["codigo"] == codigo for sup in supervisores):
            raise ValueError(
                f"O supervisor de código {codigo} não foi encontrado."
            )

        return [codigo]

    nome_procurado = normalizar_nome_filial(texto)

    candidatos = [
        sup
        for sup in supervisores
        if nome_procurado in normalizar_nome_filial(sup["nome"])
        or normalizar_nome_filial(sup["nome"]) in nome_procurado
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
                f"Encontrei mais de um supervisor parecido com "
                f"'{nome_ou_codigo}': {descricoes}. Informe o código "
                "do supervisor que deseja consultar."
            )

        return [candidato["codigo"] for candidato in candidatos]

    nome_encontrado = encontrar_filial_mais_proxima(
        nome_procurado,
        [sup["nome"] for sup in supervisores],
    )

    if nome_encontrado is not None:
        for sup in supervisores:
            if sup["nome"] == nome_encontrado:
                return [sup["codigo"]]

    raise ValueError(
        f"O supervisor '{nome_ou_codigo}' não foi encontrado."
    )
