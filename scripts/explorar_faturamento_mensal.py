from src.faturamento_data import carregar_faturamento_8280
dados = carregar_faturamento_8280()

print("Quantidade de linhas:", len(dados))
print("\nColunas encontradas:")

for coluna in dados.columns:
    print(coluna)

print("\nTipos de colunas:")
print(dados.dtypes)

dados_julho = dados[
    (dados["MES"] == 7)
    & (dados["ANO"] == 2025)
]
faturamento_julho = dados_julho["VENDA_LIQ"].sum()

print("\n=== FATURAMENTO JULHO/2025 ===")
print(faturamento_julho)

from src.faturamento_queries import (
    consultar_indicadores_faturamento,
)

resultado = consultar_indicadores_faturamento(
    meses=[7],
    anos=[2025],
)

print("\n=== CONSULTA GENÉRICA ===")
print(resultado)

resultado_timon = consultar_indicadores_faturamento(
    filiais=["FERRONORTE TIMON"],
    meses=[7],
    anos=[2025],
)

print("\n=== FATURAMENTO TIMON JULHO/2025 ===")
print(resultado_timon)

from src.faturamento_queries import listar_filiais_faturamento

filiais = listar_filiais_faturamento()

print("\n=== FILIAIS DA ROTINA 8280 ===")
for filial in filiais:
    print(filial)

from src.faturamento_tools import resolver_nome_filial

print("\n=== TESTE DE NOMES DAS FILIAIS ===")

print("Timon ->", resolver_nome_filial("Timon"))
print("Timor ->", resolver_nome_filial("Timor"))
print("Picos ->", resolver_nome_filial("Picos"))
print(
    "Campos Sales ->",
    resolver_nome_filial("Campos Sales")
)
print(
    "Santa Inês ->",
    resolver_nome_filial("Santa Inês")
)
from src.faturamento_tools import (
    executar_consulta_indicadores_faturamento,
)
print("\n=== TESTE DA FERRAMENTA GENÉRICA ===")

resultado_ferramenta = (
    executar_consulta_indicadores_faturamento(
        {
            "filiais": ["Timor"],
            "meses": [7],
            "anos": [2025],
        }
    )
)

print(resultado_ferramenta)

## teste para ver os anos disponíveis na base de dados
print("\n=== ANOS DISPONÍVEIS ===")
print(sorted(dados["ANO"].unique()))

resultado_comparacao = consultar_indicadores_faturamento(
    filiais=["FERRONORTE TIMON"],
    anos=[2022, 2023, 2024, 2025],
    agrupar_por=["ano"],
)

print("\n=== COMPARAÇÃO TIMON POR ANO ===")
print(resultado_comparacao)
