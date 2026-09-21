"""
Ponte entre a ferramenta genérica "consultar_dados_comerciais" (a
única entrada nova no catálogo de ferramentas da IA — veja
tool_manager.py) e o motor de dados (orquestrador.py).
"""
from src import orquestrador


def executar_consultar_dados_comerciais(argumentos: dict) -> dict:
    """
    Executa uma consulta genérica sobre qualquer indicador conectado
    ao motor (veja catalogo.gerar_descricao_indicadores()).

    Recebe:
    - indicador (obrigatório);
    - cruzar_com (lista de outros indicadores, juntados por filial/mês/ano);
    - colunas (campos que a tabela deve mostrar);
    - comparar_filtros (compara dois itens da mesma dimensão, ex: duas filiais);
    - periodo, periodo_personalizado;
    - filtros ({dimensao: valor(es)});
    - agrupar_por (lista de dimensões);
    - comparar_com (outro período, pra calcular crescimento);
    - filtros_calculados (filtro sobre a métrica já calculada, ex:
      "só quem bateu a meta");
    - ordenar_por (pra "os N maiores/menores" de forma exata).
    """
    consulta = {
        "indicador": argumentos.get("indicador"),
        "cruzar_com": argumentos.get("cruzar_com"),
        "colunas": argumentos.get("colunas"),
        "comparar_filtros": argumentos.get("comparar_filtros"),
        "periodo": argumentos.get("periodo"),
        "periodo_personalizado": argumentos.get("periodo_personalizado"),
        "filtros": argumentos.get("filtros") or {},
        "agrupar_por": argumentos.get("agrupar_por") or [],
        "comparar_com": argumentos.get("comparar_com"),
        "comparar_com_personalizado": argumentos.get(
            "comparar_com_personalizado"
        ),
        "filtros_calculados": argumentos.get("filtros_calculados"),
        "ordenar_por": argumentos.get("ordenar_por"),
    }

    return orquestrador.executar_consulta(consulta)
