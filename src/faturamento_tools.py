"""
Ferramentas do módulo de faturamento.

Este arquivo faz a ponte entre os nomes informados pela IA
e as consultas de faturamento.
"""
from src.faturamento_queries import (
    consultar_indicadores_faturamento,
    listar_filiais_faturamento,
)
from src.filial_utils import (
    encontrar_filial_mais_proxima,
    normalizar_nome_filial,
)

def resolver_nome_filial(nome_informado: str) -> str:
    """
    Encontra o nome correto da filial na base de faturamento.
    """

    filiais = listar_filiais_faturamento()

    if not filiais:
        raise ValueError(
            "Nenhuma filial foi encontrada "
            "na base de faturamento."
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

def executar_consulta_indicadores_faturamento(
    argumentos: dict,
) -> dict:
    """
    Executa uma consulta genérica de faturamento.

    Pode receber:
    - filiais;
    - rcas;
    - meses;
    - anos.
    """

    filiais = argumentos.get("filiais")
    rcas = argumentos.get("rcas")
    meses = argumentos.get("meses")
    anos = argumentos.get("anos")
    agrupar_por = argumentos.get("agrupar_por")

    filiais_resolvidas = None

    # Se foram informadas filiais,
    # resolve cada nome para o nome existente na base.
    if filiais:
        filiais_resolvidas = []

        for filial in filiais:
            nome_resolvido = resolver_nome_filial(
                filial
            )

            # Evita repetir a mesma filial.
            if nome_resolvido not in filiais_resolvidas:
                filiais_resolvidas.append(
                    nome_resolvido
                )

    return consultar_indicadores_faturamento(
        filiais=filiais_resolvidas,
        rcas=rcas,
        meses=meses,
        anos=anos,
        agrupar_por=agrupar_por,
    )
