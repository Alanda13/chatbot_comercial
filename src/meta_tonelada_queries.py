"""
Consultas de Meta de Tonelada.

Fonte: export do TARGIT (veja meta_tonelada_data.py). Só tem o valor
da META de tonelada — não tem o volume REALIZADO (isso está na
rotina 8280, via "consultar_indicadores_faturamento").
"""
from src.meta_tonelada_data import carregar_meta_tonelada

COLUNA_META_FILIAL = "Meta Tonelada - Filial"
COLUNA_META_RCA = "Meta Tonelada - RCA"


def _somar_meta_filial(dados) -> float:
    """
    A coluna "Meta Tonelada - Filial" se repete em toda linha de RCA
    da mesma filial/ano/mês (é um valor único por filial, não por
    vendedor) — por isso, antes de somar, precisa ficar só com uma
    linha por combinação de filial/ano/mês, senão o valor é
    multiplicado pela quantidade de RCAs daquela filial.
    """
    linhas_unicas = dados.drop_duplicates(
        subset=["FILIAL", "ANO", "MES"]
    )
    return round(float(linhas_unicas[COLUNA_META_FILIAL].sum()), 2)


def consultar_meta_tonelada(
    filiais: list[str] | None = None,
    rcas: list[str] | None = None,
    meses: list[int] | None = None,
    anos: list[int] | None = None,
    agrupar_por: list[str] | None = None,
) -> dict:
    """
    Consulta a meta de tonelada.

    Os filtros são opcionais e podem ser combinados:
    - filiais;
    - RCAs (por nome);
    - meses;
    - anos.

    Também pode agrupar os resultados por filial, RCA, mês ou ano.
    """
    dados = carregar_meta_tonelada()

    if filiais:
        dados = dados[dados["FILIAL"].isin(filiais)]

    if rcas:
        dados = dados[dados["RCA"].isin(rcas)]

    if meses:
        dados = dados[dados["MES"].isin(meses)]

    if anos:
        dados = dados[dados["ANO"].isin(anos)]

    filtros_aplicados = {
        "filiais": filiais,
        "rcas": rcas,
        "meses": meses,
        "anos": anos,
    }

    if dados.empty:
        return {
            "encontrado": False,
            "filtros_aplicados": filtros_aplicados,
            "mensagem": (
                "Nenhuma meta de tonelada encontrada para os filtros "
                "informados."
            ),
        }

    if not agrupar_por:
        return {
            "encontrado": True,
            "filtros_aplicados": filtros_aplicados,
            "meta_tonelada_filial": _somar_meta_filial(dados),
            "meta_tonelada_rca": round(
                float(dados[COLUNA_META_RCA].sum()), 2
            ),
        }

    mapa_agrupamentos = {
        "filial": "FILIAL",
        "rca": "RCA",
        "mes": "MES",
        "ano": "ANO",
    }

    colunas_agrupamento = []

    for agrupamento in agrupar_por:
        if agrupamento not in mapa_agrupamentos:
            raise ValueError(
                f"Agrupamento inválido: '{agrupamento}'."
            )

        colunas_agrupamento.append(mapa_agrupamentos[agrupamento])

    resultados = []

    for chave, grupo in dados.groupby(colunas_agrupamento, dropna=False):
        chave_tupla = chave if isinstance(chave, tuple) else (chave,)

        item = {}

        for agrupamento, valor in zip(agrupar_por, chave_tupla):
            if agrupamento in ["ano", "mes"]:
                valor = int(valor)
            else:
                valor = str(valor)

            item[agrupamento] = valor

        item["meta_tonelada_filial"] = _somar_meta_filial(grupo)
        item["meta_tonelada_rca"] = round(
            float(grupo[COLUNA_META_RCA].sum()), 2
        )

        resultados.append(item)

    return {
        "encontrado": True,
        "filtros_aplicados": filtros_aplicados,
        "agrupar_por": agrupar_por,
        "resultados": resultados,
    }
