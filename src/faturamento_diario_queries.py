"""
Consultas de indicadores de faturamento por dia.
As consultas utilizam os dados exportados da rotina 8302 do Winthor.
"""
import pandas as pd

from src.faturamento_diario_data import carregar_faturamento_8302


def consultar_indicadores_faturamento_diario(
    data_inicial: str,
    data_final: str,
    filiais: list[str] | None = None,
    rcas: list[int] | None = None,
    agrupar_por: list[str] | None = None,
) -> dict:
    """
    Consulta indicadores de faturamento da rotina 8302, com
    granularidade diária.

    O período (data_inicial/data_final) é obrigatório. Os demais
    filtros são opcionais e podem ser combinados:
    - filiais;
    - RCAs.

    Também pode agrupar os resultados por:
    - filial;
    - RCA;
    - dia;
    - forma de pagamento.
    """
    dados = carregar_faturamento_8302()

    dados = dados[
        (dados["DATA"] >= pd.to_datetime(data_inicial))
        & (dados["DATA"] <= pd.to_datetime(data_final))
    ]

    if filiais:
        dados = dados[
            dados["FILIAL"].isin(filiais)
        ]

    if rcas:
        dados = dados[
            dados["COD_RCA"].isin(rcas)
        ]

    if dados.empty:
        return {
            "encontrado": False,
            "mensagem": (
                "Nenhum dado encontrado para os filtros informados."
            ),
        }

    filtros_aplicados = {
        "data_inicial": data_inicial,
        "data_final": data_final,
        "filiais": filiais,
        "rcas": rcas,
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
            "quantidade_notas": int(
                dados["QT_NOTAS"].sum()
            ),
        }

    mapa_agrupamentos = {
        "filial": "FILIAL",
        "rca": "COD_RCA",
        "dia": "DATA",
        "forma_pagamento": "COBRANCA",
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

            if agrupamento == "dia":
                valor = valor.strftime("%Y-%m-%d")
            elif agrupamento == "rca":
                valor = int(valor)
            else:
                valor = str(valor)

            item[agrupamento] = valor

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


def listar_filiais_faturamento_diario() -> list[str]:
    """
    Retorna os nomes das filiais existentes
    na base da rotina 8302.
    """

    dados = carregar_faturamento_8302()

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
