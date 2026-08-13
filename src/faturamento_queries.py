"""
Consultas de indicadores de faturamento
As consultas utilizam os dados exportados da rotina 8280 do winthor
"""
from src.faturamento_data import carregar_faturamento_8280

def consultar_indicadores_faturamento(
        filiais: list[str]|None=None,
        rcas: list[int] | None=None,
        meses: list[int]|None=None,
        anos: list[int]|None=None        
)  -> dict:
    """
    Consulta os indicadores de faturamento
    os filtros são opcionais e podem ser combinados:
    - filiais;
    - RCAS;
    - meses;
    - anos.
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
    if dados.empty:
        return {
            "encontrado": False,
            "mensagem": "Nenhum dado encontrado para os filtros informados.",
        }
    return {
    "encontrado": True,

    "filtros_aplicados": {
        "filiais": filiais,
        "rcas": rcas,
        "meses": meses,
        "anos": anos,
    },

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
        