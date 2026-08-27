"""
Consultas de indicadores de faturamento
As consultas utilizam os dados exportados da rotina 8280 do winthor
"""
from src.faturamento_data import carregar_faturamento_8280
from src.faturamento_diario_data import construir_mapa_rca_nome

def consultar_indicadores_faturamento(
    filiais: list[str] | None = None,
    rcas: list[int] | None = None,
    meses: list[int] | None = None,
    anos: list[int] | None = None,
    agrupar_por: list[str] | None = None,
) -> dict:
    """
    Consulta indicadores de faturamento da rotina 8280.

    Os filtros são opcionais e podem ser combinados:
    - filiais;
    - RCAs;
    - meses;
    - anos.

    Também pode agrupar os resultados por:
    - filial;
    - RCA;
    - mês;
    - ano.
    """
    dados = carregar_faturamento_8280()

    if filiais:
        dados = dados[
            dados["FILIAL"].isin(filiais)
        ]

    if rcas:
        dados = dados[
            dados["COD_RCA"].isin(rcas)
        ]

    if meses:
        dados = dados[
            dados["MES"].isin(meses)
        ]

    if anos:
        dados = dados[
            dados["ANO"].isin(anos)
        ]

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
                "Nenhum dado encontrado para os filtros informados."
            ),
        }

    # Se não foi solicitado agrupamento,
    # retorna o total agregado normalmente.
    if not agrupar_por:
        return {
            "encontrado": True,
            "filtros_aplicados": filtros_aplicados,
            "faturamento": round(
                float(dados["VENDA_LIQ"].sum()),
                2,
            ),
            "venda_bruta": round(
                float(dados["VENDA_BRUTA"].sum()),
                2,
            ),
            "valor_desconto": round(
                float(dados["VALORDESC"].sum()),
                2,
            ),
            "peso_liquido": round(
                float(dados["PESOLIQ"].sum()),
                2,
            ),
            "quantidade_notas": int(
                dados["QT_NOTAS"].sum()
            ),
        }

    mapa_agrupamentos = {
        "filial": "FILIAL",
        "rca": "COD_RCA",
        "mes": "MES",
        "ano": "ANO",
    }

    colunas_agrupamento = []

    for agrupamento in agrupar_por:
        if agrupamento not in mapa_agrupamentos:
            raise ValueError(
                f"Agrupamento inválido: '{agrupamento}'."
            )

        colunas_agrupamento.append(
            mapa_agrupamentos[agrupamento]
        )

    mapa_rca_nome = {}

    if "rca" in agrupar_por:
        try:
            mapa_rca_nome = construir_mapa_rca_nome()
        except FileNotFoundError:
            mapa_rca_nome = {}

    agrupado = (
        dados
        .groupby(
            colunas_agrupamento,
            dropna=False,
        )
        .agg(
            faturamento=("VENDA_LIQ", "sum"),
            venda_bruta=("VENDA_BRUTA", "sum"),
            valor_desconto=("VALORDESC", "sum"),
            peso_liquido=("PESOLIQ", "sum"),
            quantidade_notas=("QT_NOTAS", "sum"),
        )
        .reset_index()
    )

    resultados = []

    for _, linha in agrupado.iterrows():
        item = {}

        for agrupamento, coluna in zip(
            agrupar_por,
            colunas_agrupamento,
        ):
            valor = linha[coluna]

            if agrupamento in ["ano", "mes", "rca"] :
                valor = int(valor)
            else:
                valor = str(valor)

            item[agrupamento] = valor

            if agrupamento == "rca":
                item["rca_nome"] = mapa_rca_nome.get(valor)

        item["faturamento"] = round(
            float(linha["faturamento"]),
            2,
        )

        item["venda_bruta"] = round(
            float(linha["venda_bruta"]),
            2,
        )

        item["valor_desconto"] = round(
            float(linha["valor_desconto"]),
            2,
        )

        item["peso_liquido"] = round(
            float(linha["peso_liquido"]),
            2,
        )

        item["quantidade_notas"] = int(
            linha["quantidade_notas"]
        )

        resultados.append(item)

    return {
        "encontrado": True,
        "filtros_aplicados": filtros_aplicados,
        "agrupar_por": agrupar_por,
        "resultados": resultados,
    }

def listar_filiais_faturamento() -> list[str]:
    """
    Retorna os nomes das filiais existentes
    na base da rotina 8280.
    """

    dados = carregar_faturamento_8280()

    filiais = (
        dados["FILIAL"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )

    filiais.sort()

    return filiais