from pprint import pprint

from src.queries import (
    obter_resumo_nps,
    listar_filiais,
    obter_nps_por_filial,
    obter_nps_por_periodo,
    comparar_nps_entre_periodos,
)
def testar_resumo_nps():
    resumo = obter_resumo_nps()
    print("\n=== RESUMO DO NPS ===\n")
    pprint(resumo)

def testar_filiais():
    print("\n=== FILIAIS ===\n")
    filiais = listar_filiais()
    pprint(filiais)

def testar_nps_por_filial():
    print("\n=== NPS POR FILIAL ===\n")
    filiais = obter_nps_por_filial()
    pprint(filiais)

def testar_nps_por_periodo():
    resultado = obter_nps_por_periodo(
        "2026-07-01",
        "2026-07-31",
    )
    print("\n=== NPS POR PERÍODO ===\n")
    pprint(resultado)

def testar_comparacao_nps():
    print("\n=== COMPARAÇÃO DE NPS ===\n")

    resultado = comparar_nps_entre_periodos(
        "2026-07-01",
        "2026-07-31",
        "2026-06-01",
        "2026-06-30",
    )

    pprint(resultado)

if __name__ == "__main__":
    try:
        testar_resumo_nps()
        testar_filiais()
        testar_nps_por_filial()
        testar_nps_por_periodo()
        testar_comparacao_nps()

    except Exception as error:
        print("Ocorreu um erro durante o teste:")
        print(error)