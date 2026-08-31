"""
Ferramentas do módulo de faturamento diário (rotina 8302).

Este arquivo faz a ponte entre os nomes informados pela IA
e as consultas de faturamento por dia.
"""
from src.faturamento_diario_queries import (
    consultar_indicadores_faturamento_diario,
    listar_filiais_faturamento_diario,
)
from src.faturamento_diario_data import (
    construir_mapa_rca_nome,
    resolver_codigo_rca,
)
from src.filial_utils import (
    encontrar_filial_mais_proxima,
    normalizar_nome_filial,
)


def resolver_nome_filial_diario(nome_informado: str) -> str:
    """
    Encontra o nome correto da filial na base de faturamento diário.
    """

    filiais = listar_filiais_faturamento_diario()

    if not filiais:
        raise ValueError(
            "Nenhuma filial foi encontrada "
            "na base de faturamento diário."
        )

    nome_procurado = normalizar_nome_filial(
        nome_informado
    )

    filial_encontrada = encontrar_filial_mais_proxima(
        nome_procurado,
        filiais,
    )

    if filial_encontrada is None:
        raise ValueError(
            f"A filial '{nome_informado}' não foi encontrada."
        )

    return filial_encontrada


def executar_consulta_indicadores_faturamento_diario(
    argumentos: dict,
) -> dict:
    """
    Executa uma consulta genérica de faturamento diário (rotina 8302).

    Pode receber:
    - periodos (obrigatório): lista de {"data_inicial", "data_final"};
    - filiais;
    - rcas;
    - agrupar_por.
    """

    periodos = argumentos.get("periodos")

    if not periodos:
        raise ValueError(
            "O período (\"periodos\") é obrigatório para consultar "
            "o faturamento diário — informe ao menos uma data "
            "inicial e final."
        )

    filiais = argumentos.get("filiais")
    rcas = argumentos.get("rcas")
    agrupar_por = argumentos.get("agrupar_por")

    filiais_resolvidas = None

    if filiais:
        filiais_resolvidas = []

        for filial in filiais:
            nome_resolvido = resolver_nome_filial_diario(
                filial
            )

            if nome_resolvido not in filiais_resolvidas:
                filiais_resolvidas.append(
                    nome_resolvido
                )

    rcas_resolvidos = None

    # Os RCAs podem vir como código numérico ou como nome do
    # vendedor — resolve cada um para o código real.
    if rcas:
        rcas_resolvidos = []

        for rca in rcas:
            codigo_resolvido = resolver_codigo_rca(
                rca,
                filiais=filiais_resolvidas,
            )

            if codigo_resolvido not in rcas_resolvidos:
                rcas_resolvidos.append(
                    codigo_resolvido
                )

    resultados = [
        consultar_indicadores_faturamento_diario(
            data_inicial=periodo["data_inicial"],
            data_final=periodo["data_final"],
            filiais=filiais_resolvidas,
            rcas=rcas_resolvidos,
            agrupar_por=agrupar_por,
        )
        for periodo in periodos
    ]

    if rcas_resolvidos:
        mapa_rca_nome = construir_mapa_rca_nome()
        rcas_identificados = [
            f"{mapa_rca_nome.get(codigo, 'nome não identificado')} "
            f"(código {codigo})"
            for codigo in rcas_resolvidos
        ]

        for resultado in resultados:
            resultado.setdefault("filtros_aplicados", {})[
                "rcas_identificados"
            ] = rcas_identificados

    if len(resultados) == 1:
        return resultados[0]

    return {
        "filiais": filiais_resolvidas,
        "periodos": resultados,
    }
