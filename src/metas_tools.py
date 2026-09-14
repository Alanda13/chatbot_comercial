"""
Ferramentas do módulo de Metas.

Este arquivo faz a ponte entre os nomes informados pela IA
e a consulta de metas.
"""
from src.metas_queries import (
    consultar_metas,
    consultar_crescimento_abaixo_meta,
)
from src.metas_data import resolver_codigos_supervisor
from src.faturamento_diario_data import resolver_codigos_rca
from src.faturamento_tools import resolver_nome_filial


def _resolver_filtros(argumentos: dict) -> tuple:
    """
    Resolve filiais, rcas e supervisores informados pela IA para os
    valores reais usados na base (mesma lógica usada em
    executar_consultar_metas).
    """
    filiais = argumentos.get("filiais")
    rcas = argumentos.get("rcas")
    supervisores = argumentos.get("supervisores")

    filiais_resolvidas = None

    if filiais:
        filiais_resolvidas = []

        for filial in filiais:
            nome_resolvido = resolver_nome_filial(filial)

            if nome_resolvido not in filiais_resolvidas:
                filiais_resolvidas.append(nome_resolvido)

    rcas_resolvidos = None

    if rcas:
        rcas_resolvidos = []

        for rca in rcas:
            for codigo in resolver_codigos_rca(
                rca,
                filiais=filiais_resolvidas,
            ):
                if codigo not in rcas_resolvidos:
                    rcas_resolvidos.append(codigo)

    supervisores_resolvidos = None

    if supervisores:
        supervisores_resolvidos = []

        for supervisor in supervisores:
            for codigo in resolver_codigos_supervisor(
                supervisor,
                filiais=filiais_resolvidas,
            ):
                if codigo not in supervisores_resolvidos:
                    supervisores_resolvidos.append(codigo)

    return filiais_resolvidas, rcas_resolvidos, supervisores_resolvidos


def executar_consultar_metas(argumentos: dict) -> dict:
    """
    Executa uma consulta genérica de metas.

    Pode receber:
    - filiais;
    - rcas;
    - supervisores;
    - meses;
    - anos;
    - agrupar_por;
    - apenas_rcas_com_meta (padrão True): quando agrupar_por inclui
      "rca" e nenhum RCA específico foi informado, filtra o resultado
      pra trazer só os RCAs com meta cadastrada (vendedores de
      verdade) — mesma definição usada em listar_rcas_filial e no
      filtro equivalente de consultar_indicadores_faturamento. Sem
      isso, contas genéricas/contábeis (ex: "matriz"), que aparecem na
      base com faturamento e meta zerados, podiam "ganhar" como o RCA
      de menor faturamento.
    """

    meses = argumentos.get("meses")
    anos = argumentos.get("anos")
    agrupar_por = argumentos.get("agrupar_por")
    apenas_rcas_com_meta = argumentos.get("apenas_rcas_com_meta", True)

    filiais_resolvidas, rcas_resolvidos, supervisores_resolvidos = (
        _resolver_filtros(argumentos)
    )

    resultado = consultar_metas(
        filiais=filiais_resolvidas,
        rcas=rcas_resolvidos,
        supervisores=supervisores_resolvidos,
        meses=meses,
        anos=anos,
        agrupar_por=agrupar_por,
    )

    if (
        not rcas_resolvidos
        and agrupar_por
        and "rca" in agrupar_por
        and apenas_rcas_com_meta
        and resultado.get("encontrado")
    ):
        resultados_filtrados = [
            item for item in resultado["resultados"]
            if item.get("valor_meta")
        ]

        if not resultados_filtrados:
            return {
                "encontrado": False,
                "filtros_aplicados": resultado.get("filtros_aplicados"),
                "mensagem": (
                    "Nenhum RCA com meta cadastrada encontrado para "
                    "esses filtros."
                ),
            }

        resultado = {**resultado, "resultados": resultados_filtrados}

    return resultado


def executar_consultar_crescimento_abaixo_meta(argumentos: dict) -> dict:
    """
    Executa a consulta de filiais/RCAs/supervisores que cresceram em
    faturamento em relação ao ano anterior e ainda estão abaixo da
    meta no ano informado.

    Recebe:
    - ano (obrigatório);
    - filiais, rcas, supervisores (opcionais);
    - agrupar_por: "filial" (padrão), "rca" ou "supervisor".
    """
    ano = argumentos.get("ano")
    agrupar_por = argumentos.get("agrupar_por") or "filial"

    if isinstance(agrupar_por, list):
        agrupar_por = agrupar_por[0] if agrupar_por else "filial"

    filiais_resolvidas, rcas_resolvidos, supervisores_resolvidos = (
        _resolver_filtros(argumentos)
    )

    return consultar_crescimento_abaixo_meta(
        ano=ano,
        filiais=filiais_resolvidas,
        rcas=rcas_resolvidos,
        supervisores=supervisores_resolvidos,
        agrupar_por=agrupar_por,
    )
def executar_listar_rcas_filial(argumentos: dict) -> dict:
    """
    Lista os RCAs (vendedores) que têm meta cadastrada em uma ou mais
    filiais — essa é a definição de "RCA de uma filial" usada no
    projeto. Reaproveita consultar_metas agrupando por RCA, mas
    devolve só a identificação (nome e código), sem valores de meta,
    já que essa ferramenta é só para listagem.
    """
    anos = argumentos.get("anos")

    filiais_resolvidas, _, _ = _resolver_filtros(argumentos)

    resultado = consultar_metas(
        filiais=filiais_resolvidas,
        anos=anos,
        agrupar_por=["rca"],
    )

    if not resultado.get("encontrado"):
        return {
            "encontrado": False,
            "filiais": filiais_resolvidas,
            "mensagem": resultado.get(
                "mensagem", "Nenhum RCA encontrado para essa filial."
            ),
        }

    rcas_listados = [
        {
            "codigo": item["rca"],
            "rca": item.get("rca_nome") or f"RCA {item['rca']}",
        }
        for item in resultado["resultados"]
        if item.get("valor_meta")
    ]

    rcas_listados.sort(key=lambda item: item["rca"] or "")

    return {
        "encontrado": True,
        "filiais": filiais_resolvidas,
        "anos": anos,
        "resultados": rcas_listados,
    }
