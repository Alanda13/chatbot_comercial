"""
Ferramentas do módulo de faturamento.

Este arquivo faz a ponte entre os nomes informados pela IA
e as consultas de faturamento.
"""
from src.faturamento_queries import (
    consultar_indicadores_faturamento,
    listar_filiais_faturamento,
)
from src.faturamento_diario_data import (
    construir_mapa_rca_nome,
    resolver_codigos_rca,
    verificar_rca,
)
from src.filial_utils import (
    encontrar_filial_mais_proxima,
    normalizar_nome_filial,
)
from src.metas_queries import consultar_metas

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
    - anos;
    - agrupar_por;
    - apenas_rcas_com_meta (padrão True): quando agrupar_por inclui
      "rca" e nenhum RCA específico foi informado, filtra para trazer
      só os RCAs com meta cadastrada na filial (vendedores de
      verdade). Passe False para trazer TODOS os códigos que
      apareceram na base de faturamento, mesmo sem meta cadastrada.
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

    rcas_resolvidos = None

    # Os RCAs podem vir como código numérico ou como nome do
    # vendedor — resolve cada um para o código real.
    if rcas:
        rcas_resolvidos = []

        for rca in rcas:
            codigos_resolvidos = resolver_codigos_rca(
                rca,
                filiais=filiais_resolvidas,
            )

            for codigo in codigos_resolvidos:
                if codigo not in rcas_resolvidos:
                    rcas_resolvidos.append(codigo)

    apenas_rcas_com_meta = argumentos.get("apenas_rcas_com_meta", True)

    # Se a pergunta pede o detalhamento por RCA (agrupar_por inclui
    # "rca") mas não especificou quais RCAs, usa só os RCAs que têm
    # meta cadastrada na filial — a mesma definição de "RCA de uma
    # filial" usada em listar_rcas_filial. Sem isso, a consulta traz
    # qualquer código que apareceu na base de faturamento, mesmo
    # contas genéricas/contábeis que não são vendedores de verdade.
    # Esse filtro pode ser desativado (apenas_rcas_com_meta=False)
    # quando o usuário pedir explicitamente TODOS que venderam.
    if (
        not rcas_resolvidos
        and agrupar_por
        and "rca" in agrupar_por
        and filiais_resolvidas
        and apenas_rcas_com_meta
    ):
        resultado_metas = consultar_metas(
            filiais=filiais_resolvidas,
            anos=anos,
            agrupar_por=["rca"],
        )

        if resultado_metas.get("encontrado"):
            rcas_resolvidos = [
                item["rca"]
                for item in resultado_metas["resultados"]
                if item.get("valor_meta")
            ]

    resultado = consultar_indicadores_faturamento(
        filiais=filiais_resolvidas,
        rcas=rcas_resolvidos,
        meses=meses,
        anos=anos,
        agrupar_por=agrupar_por,
    )

    if rcas_resolvidos:
        mapa_rca_nome = construir_mapa_rca_nome()
        resultado.setdefault("filtros_aplicados", {})[
            "rcas_identificados"
        ] = [
            f"{mapa_rca_nome.get(codigo, 'nome não identificado')} "
            f"(código {codigo})"
            for codigo in rcas_resolvidos
        ]

        # Quando o resultado é agrupado por RCA, cada linha traz só o
    # código — adiciona o nome do vendedor em cada linha também, pra
    # não depender só do texto que a IA escreve (a tabela precisa
    # disso pra mostrar o nome, não só o código cru).
    lista_resultados = resultado.get("resultados")

    if isinstance(lista_resultados, list) and any(
        isinstance(item, dict) and "rca" in item
        for item in lista_resultados
    ):
        mapa_rca_nome = construir_mapa_rca_nome()

        for item in lista_resultados:
            if isinstance(item, dict) and "rca" in item:
                item["rca_nome"] = mapa_rca_nome.get(item["rca"])

    # Quando o usuário pede explicitamente "quem vendeu" (não quer
    # ver quem ficou zerado), remove os RCAs com faturamento exatamente
    # R$ 0,00 do resultado.
    excluir_sem_venda = argumentos.get("excluir_sem_venda", False)

    if excluir_sem_venda and isinstance(lista_resultados, list):
        resultado["resultados"] = [
            item for item in lista_resultados
            if item.get("faturamento") not in (0, 0.0, None)
        ]

    return resultado


def executar_verificar_rca(argumentos: dict) -> dict:
    """
    Verifica se um RCA (por nome ou código) existe, sem exigir
    período — usada para confirmar o RCA antes de pedir o período ao
    usuário.
    """

    rca = argumentos.get("rca")

    if not rca:
        raise ValueError(
            "Informe o nome ou o código do RCA que deseja verificar."
        )

    filiais = argumentos.get("filiais")

    filiais_resolvidas = None

    if filiais:
        filiais_resolvidas = []

        for filial in filiais:
            nome_resolvido = resolver_nome_filial(filial)

            if nome_resolvido not in filiais_resolvidas:
                filiais_resolvidas.append(nome_resolvido)

    return verificar_rca(rca, filiais=filiais_resolvidas)