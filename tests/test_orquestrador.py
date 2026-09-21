from datetime import date

import pandas as pd
import pytest

from src import catalogo
from src import motor_metricas
from src import orquestrador as orq
from src.exceptions import ConsultaInvalida


def _dados_faturamento():
    return pd.DataFrame(
        [
            {
                "FILIAL": "TIMON",
                "COD_RCA": 8403,
                "MES": 7,
                "ANO": 2025,
                "VENDA_LIQ": 100.0,
                "VENDA_BRUTA": 110.0,
                "VALORDESC": 10.0,
                "PESOLIQ": 200.0,
                "QT_NOTAS": 5,
            },
            {
                "FILIAL": "TIMON",
                "COD_RCA": 8403,
                "MES": 7,
                "ANO": 2024,
                "VENDA_LIQ": 80.0,
                "VENDA_BRUTA": 90.0,
                "VALORDESC": 10.0,
                "PESOLIQ": 150.0,
                "QT_NOTAS": 4,
            },
        ]
    )


def _dados_meta():
    return pd.DataFrame(
        [
            {
                "FILIAL": "TIMON",
                "COD_RCA": 8403,
                "COD_SUPERVISOR": 9,
                "MES": 7,
                "ANO": 2025,
                "VENDA_LIQ": 80000.0,
                "VALOR_META": 100000.0,
            },
            {
                "FILIAL": "TIBIRI",
                "COD_RCA": 9138,
                "COD_SUPERVISOR": 11,
                "MES": 7,
                "ANO": 2025,
                "VENDA_LIQ": 50000.0,
                "VALOR_META": 40000.0,
            },
        ]
    )


# --- validar_consulta ---


def test_validar_consulta_rejeita_indicador_inexistente():
    with pytest.raises(ConsultaInvalida):
        orq.validar_consulta({"indicador": "inexistente"})


def test_validar_consulta_rejeita_dimensao_fora_do_catalogo():
    with pytest.raises(ConsultaInvalida):
        orq.validar_consulta(
            {"indicador": "faturamento", "agrupar_por": ["produto"]}
        )


def test_validar_consulta_rejeita_filtro_fora_do_catalogo():
    with pytest.raises(ConsultaInvalida):
        orq.validar_consulta(
            {"indicador": "faturamento", "filtros": {"produto": ["X"]}}
        )


def test_validar_consulta_rejeita_campo_invalido_em_ordenar_por():
    with pytest.raises(ConsultaInvalida):
        orq.validar_consulta(
            {
                "indicador": "faturamento",
                "ordenar_por": {"campo": "campo_inexistente"},
            }
        )


def test_validar_consulta_aceita_campo_de_comparacao_em_ordenar_por():
    """
    Regressão: "ordenar_por" rejeitava campos como
    "diferenca_faturamento_realizado", que só existem quando
    "comparar_com" é usado — não vêm do catálogo estático, são
    criados em tempo de execução. Não pode levantar erro.
    """
    orq.validar_consulta(
        {
            "indicador": "meta",
            "agrupar_por": ["filial"],
            "comparar_com": "ano_anterior_ao_filtro",
            "ordenar_por": {
                "campo": "diferenca_faturamento_realizado",
                "ordem": "desc",
                "limite": 1,
            },
        }
    )


def test_validar_consulta_ainda_rejeita_campo_de_comparacao_sem_comparar_com():
    with pytest.raises(ConsultaInvalida):
        orq.validar_consulta(
            {
                "indicador": "meta",
                "agrupar_por": ["filial"],
                "ordenar_por": {"campo": "diferenca_faturamento_realizado"},
            }
        )


def test_validar_consulta_rejeita_periodo_desconhecido():
    with pytest.raises(ConsultaInvalida):
        orq.validar_consulta(
            {"indicador": "faturamento", "periodo": "semestre_passado"}
        )


# --- resolver_periodo ---


def test_resolver_periodo_personalizado_mensal():
    filtro = orq.resolver_periodo(
        "personalizado", {"meses": [7], "anos": [2025]}, "mensal"
    )
    assert filtro == {"mes": [7], "ano": [2025]}


def test_resolver_periodo_personalizado_diaria():
    filtro = orq.resolver_periodo(
        "personalizado",
        {"data_inicial": "2025-07-01", "data_final": "2025-07-31"},
        "diaria",
    )
    assert filtro == {
        "dia": {"data_inicial": "2025-07-01", "data_final": "2025-07-31"}
    }


def test_resolver_periodo_personalizado_sem_dados_gera_erro():
    with pytest.raises(ConsultaInvalida):
        orq.resolver_periodo("personalizado", None, "mensal")


def test_resolver_periodo_nao_suportado_gera_erro():
    with pytest.raises(ConsultaInvalida):
        orq.resolver_periodo("trimestre_atual", None, "mensal")


# --- executar_consulta: indicador sem fonte real conectada ---


def test_executar_consulta_indicador_sem_fonte_real_gera_erro():
    with pytest.raises(ConsultaInvalida):
        orq.executar_consulta({"indicador": "desconto"})


# --- executar_consulta: faturamento ---


def test_executar_consulta_faturamento_sem_agrupamento(monkeypatch):
    monkeypatch.setitem(
        catalogo.INDICADORES["faturamento"], "carregar", _dados_faturamento
    )

    resultado = orq.executar_consulta(
        {"indicador": "faturamento", "filtros": {"ano": [2025]}}
    )

    assert resultado["encontrado"] is True
    assert resultado["resultados"] == [
        {
            "faturamento": 100.0,
            "venda_bruta": 110.0,
            "valor_desconto": 10.0,
            "peso_liquido": 200.0,
            "quantidade_notas": 5.0,
            "toneladas": 0.2,
        }
    ]


def test_executar_consulta_faturamento_sem_dado_retorna_nao_encontrado(
    monkeypatch,
):
    monkeypatch.setitem(
        catalogo.INDICADORES["faturamento"], "carregar", _dados_faturamento
    )

    resultado = orq.executar_consulta(
        {"indicador": "faturamento", "filtros": {"ano": [2019]}}
    )

    assert resultado["encontrado"] is False
    assert resultado["resultados"] == []


def test_executar_consulta_faturamento_agrupado_por_filial(monkeypatch):
    monkeypatch.setitem(
        catalogo.INDICADORES["faturamento"], "carregar", _dados_faturamento
    )

    resultado = orq.executar_consulta(
        {
            "indicador": "faturamento",
            "filtros": {"ano": [2025]},
            "agrupar_por": ["filial"],
        }
    )

    assert resultado["resultados"][0]["filial"] == "TIMON"
    assert resultado["resultados"][0]["faturamento"] == 100.0


def test_executar_consulta_comparar_com_calcula_variacao(monkeypatch):
    monkeypatch.setitem(
        catalogo.INDICADORES["faturamento"], "carregar", _dados_faturamento
    )

    def resolver_periodo_fake(periodo, personalizado, granularidade):
        if periodo == "ano_atual":
            return {"ano": [2025]}
        if periodo == "mesmo_mes_ano_anterior":
            return {"ano": [2024]}
        raise AssertionError(f"período inesperado: {periodo}")

    monkeypatch.setattr(orq, "resolver_periodo", resolver_periodo_fake)

    resultado = orq.executar_consulta(
        {
            "indicador": "faturamento",
            "periodo": "ano_atual",
            "comparar_com": "mesmo_mes_ano_anterior",
        }
    )

    item = resultado["resultados"][0]
    assert item["faturamento"] == 100.0
    assert item["faturamento_anterior"] == 80.0
    assert item["diferenca_faturamento"] == 20.0
    assert item["percentual_faturamento"] == 25.0


def test_executar_consulta_comparar_com_ano_anterior_ao_filtro(monkeypatch):
    monkeypatch.setitem(
        catalogo.INDICADORES["faturamento"], "carregar", _dados_faturamento
    )

    resultado = orq.executar_consulta(
        {
            "indicador": "faturamento",
            "filtros": {"ano": [2025]},
            "comparar_com": "ano_anterior_ao_filtro",
        }
    )

    item = resultado["resultados"][0]
    assert item["faturamento"] == 100.0
    assert item["faturamento_anterior"] == 80.0
    assert item["percentual_faturamento"] == 25.0


def test_ano_anterior_ao_filtro_sem_ano_nos_filtros_gera_erro(monkeypatch):
    monkeypatch.setitem(
        catalogo.INDICADORES["faturamento"], "carregar", _dados_faturamento
    )

    with pytest.raises(ConsultaInvalida):
        orq.executar_consulta(
            {
                "indicador": "faturamento",
                "comparar_com": "ano_anterior_ao_filtro",
            }
        )


def test_comparar_com_reaproveita_mesmo_conjunto_de_rcas_validos(monkeypatch):
    """
    Regressão: um RCA com meta cadastrada no ano atual mas SEM meta
    cadastrada no ano anterior não pode perder o faturamento_realizado
    do ano anterior inteiro — senão o crescimento sai errado (parece
    que não tinha dado nenhum pra comparar). O conjunto de RCAs
    "válidos" precisa ser o mesmo nas duas consultas (calculado a
    partir do ano principal), não recalculado por ano.
    """
    dados_meta = pd.DataFrame(
        [
            # RCA 1: tem meta nos dois anos.
            {"FILIAL": "TIMON", "COD_RCA": 1, "MES": 1, "ANO": 2024, "VENDA_LIQ": 100.0, "VALOR_META": 90.0},
            {"FILIAL": "TIMON", "COD_RCA": 1, "MES": 1, "ANO": 2025, "VENDA_LIQ": 150.0, "VALOR_META": 120.0},
            # RCA 2: só tem meta cadastrada em 2025 (começou este ano),
            # mas já tinha faturamento em 2024 (ex: como RCA genérico).
            {"FILIAL": "TIMON", "COD_RCA": 2, "MES": 1, "ANO": 2024, "VENDA_LIQ": 50.0, "VALOR_META": 0.0},
            {"FILIAL": "TIMON", "COD_RCA": 2, "MES": 1, "ANO": 2025, "VENDA_LIQ": 200.0, "VALOR_META": 100.0},
        ]
    )
    monkeypatch.setitem(catalogo.INDICADORES["meta"], "carregar", lambda: dados_meta)

    resultado = orq.executar_consulta(
        {
            "indicador": "meta",
            "filtros": {"ano": [2025]},
            "agrupar_por": ["rca"],
            "comparar_com": "ano_anterior_ao_filtro",
        }
    )

    por_rca = {item["rca"]: item for item in resultado["resultados"]}

    assert por_rca[2]["faturamento_realizado_anterior"] == 50.0
    assert por_rca[2]["diferenca_faturamento_realizado"] == 150.0


# --- executar_consulta: meta (derivados + filtros_calculados) ---


def test_executar_consulta_faturamento_agrupado_por_rca_traz_nome(monkeypatch):
    dados = pd.DataFrame(
        [
            {
                "FILIAL": "TIMON", "COD_RCA": 8403, "MES": 7,
                "ANO": 2025, "VENDA_LIQ": 100.0, "VENDA_BRUTA": 0,
                "VALORDESC": 0, "PESOLIQ": 0, "QT_NOTAS": 0,
            },
        ]
    )
    monkeypatch.setitem(catalogo.INDICADORES["faturamento"], "carregar", lambda: dados)
    monkeypatch.setitem(
        catalogo.INDICADORES["faturamento"],
        "rca_nome_mapa",
        lambda: {8403: "Alfredo Sousa-F09"},
    )
    # RCA explícito, pra não disparar a checagem de meta cadastrada
    # (não é o que esse teste cobre).
    monkeypatch.setitem(catalogo.INDICADORES["faturamento"], "rca_requer_meta_cadastrada", False)

    resultado = orq.executar_consulta(
        {
            "indicador": "faturamento",
            "filtros": {"filial": ["TIMON"], "mes": [7], "ano": [2025]},
            "agrupar_por": ["rca"],
        }
    )

    assert resultado["resultados"][0]["rca_nome"] == "Alfredo Sousa-F09"


def test_executar_consulta_agrupado_por_rca_filtra_sem_meta_cadastrada(
    monkeypatch,
):
    dados_faturamento_teste = pd.DataFrame(
        [
            {
                "FILIAL": "TIMON", "COD_RCA": 1, "MES": 7,
                "ANO": 2025, "VENDA_LIQ": 100.0, "VENDA_BRUTA": 0,
                "VALORDESC": 0, "PESOLIQ": 0, "QT_NOTAS": 0,
            },
            {
                "FILIAL": "TIMON", "COD_RCA": 2, "MES": 7,
                "ANO": 2025, "VENDA_LIQ": 50.0, "VENDA_BRUTA": 0,
                "VALORDESC": 0, "PESOLIQ": 0, "QT_NOTAS": 0,
            },
        ]
    )
    dados_meta_teste = pd.DataFrame(
        [
            # RCA 1 tem meta cadastrada; RCA 2 não (conta genérica).
            {
                "FILIAL": "TIMON", "COD_RCA": 1, "MES": 7,
                "ANO": 2025, "VENDA_LIQ": 100.0, "VALOR_META": 90.0,
            },
            {
                "FILIAL": "TIMON", "COD_RCA": 2, "MES": 7,
                "ANO": 2025, "VENDA_LIQ": 50.0, "VALOR_META": 0.0,
            },
        ]
    )
    monkeypatch.setitem(
        catalogo.INDICADORES["faturamento"], "carregar", lambda: dados_faturamento_teste
    )
    monkeypatch.setitem(
        catalogo.INDICADORES["meta"], "carregar", lambda: dados_meta_teste
    )

    resultado = orq.executar_consulta(
        {
            "indicador": "faturamento",
            "filtros": {"filial": ["TIMON"], "mes": [7], "ano": [2025]},
            "agrupar_por": ["rca"],
        }
    )

    codigos = [item["rca"] for item in resultado["resultados"]]
    assert codigos == [1]


def test_executar_consulta_agrupado_por_rca_com_rca_explicito_nao_filtra(
    monkeypatch,
):
    dados_faturamento_teste = pd.DataFrame(
        [
            {
                "FILIAL": "TIMON", "COD_RCA": 2, "MES": 7,
                "ANO": 2025, "VENDA_LIQ": 50.0, "VENDA_BRUTA": 0,
                "VALORDESC": 0, "PESOLIQ": 0, "QT_NOTAS": 0,
            },
        ]
    )
    dados_meta_teste = pd.DataFrame(
        [
            {
                "FILIAL": "TIMON", "COD_RCA": 2, "MES": 7,
                "ANO": 2025, "VENDA_LIQ": 50.0, "VALOR_META": 0.0,
            },
        ]
    )
    monkeypatch.setitem(
        catalogo.INDICADORES["faturamento"], "carregar", lambda: dados_faturamento_teste
    )
    monkeypatch.setitem(
        catalogo.INDICADORES["meta"], "carregar", lambda: dados_meta_teste
    )
    monkeypatch.setitem(
        catalogo.INDICADORES["faturamento"]["resolver_dimensao"],
        "rca",
        lambda codigo, filiais=None: [codigo],
    )

    # RCA pedido explicitamente (mesmo sem meta cadastrada) não deve
    # ser filtrado — só filtra quando a IA NÃO especifica RCA nenhum.
    resultado = orq.executar_consulta(
        {
            "indicador": "faturamento",
            "filtros": {
                "filial": ["TIMON"], "mes": [7], "ano": [2025],
                "rca": [2],
            },
            "agrupar_por": ["rca"],
        }
    )

    assert [item["rca"] for item in resultado["resultados"]] == [2]


def test_executar_consulta_meta_aplica_derivados(monkeypatch):
    monkeypatch.setitem(catalogo.INDICADORES["meta"], "carregar", _dados_meta)

    resultado = orq.executar_consulta(
        {
            "indicador": "meta",
            "filtros": {"mes": [7], "ano": [2025]},
            "agrupar_por": ["filial"],
        }
    )

    por_filial = {item["filial"]: item for item in resultado["resultados"]}

    assert por_filial["TIMON"]["percentual_atingimento"] == 80.0
    assert por_filial["TIMON"]["falta_para_meta"] == 20000.0
    assert por_filial["TIBIRI"]["percentual_atingimento"] == 125.0
    assert por_filial["TIBIRI"]["falta_para_meta"] == 0.0


def test_executar_consulta_meta_mes_e_ano_calcula_variacao_ano_anterior(
    monkeypatch,
):
    dados = pd.DataFrame(
        [
            {
                "FILIAL": "TIMON",
                "COD_RCA": 8403,
                "COD_SUPERVISOR": 9,
                "MES": 7,
                "ANO": 2024,
                "VENDA_LIQ": 80.0,
                "VALOR_META": 100.0,
            },
            {
                "FILIAL": "TIMON",
                "COD_RCA": 8403,
                "COD_SUPERVISOR": 9,
                "MES": 7,
                "ANO": 2025,
                "VENDA_LIQ": 100.0,
                "VALOR_META": 110.0,
            },
        ]
    )
    monkeypatch.setitem(catalogo.INDICADORES["meta"], "carregar", lambda: dados)

    resultado = orq.executar_consulta(
        {
            "indicador": "meta",
            "filtros": {"ano": [2024, 2025]},
            "agrupar_por": ["mes", "ano"],
        }
    )

    por_ano = {item["ano"]: item for item in resultado["resultados"]}

    assert por_ano[2024]["percentual_ano_anterior"] is None
    assert por_ano[2025]["faturamento_realizado_ano_anterior"] == 80.0
    assert por_ano[2025]["diferenca_ano_anterior"] == 20.0
    assert por_ano[2025]["percentual_ano_anterior"] == 25.0


def test_aplicar_agrupamento_campo_unico_por_nao_multiplica_valor_repetido(
    monkeypatch,
):
    """
    Regressão do problema real do meta_tonelada: um campo cujo valor se
    repete em toda linha de RCA da mesma filial/mês (ex: meta por
    filial) não pode ser somado direto — precisa descartar as
    duplicatas antes, senão o valor sai multiplicado pela quantidade de
    RCAs daquela filial. Registra um indicador de teste com essa opção
    ("unico_por") e confere que o valor final bate com o esperado, não
    com o valor multiplicado.
    """
    dados = pd.DataFrame(
        [
            # 3 linhas de RCA pra mesma filial/mês, com a "meta da
            # filial" repetida (100.0) e a "meta do RCA" própria de
            # cada linha.
            {"FILIAL": "TIMON", "RCA": "RCA A", "MES": 7, "ANO": 2025, "META_FILIAL": 100.0, "META_RCA": 30.0},
            {"FILIAL": "TIMON", "RCA": "RCA B", "MES": 7, "ANO": 2025, "META_FILIAL": 100.0, "META_RCA": 40.0},
            {"FILIAL": "TIMON", "RCA": "RCA C", "MES": 7, "ANO": 2025, "META_FILIAL": 100.0, "META_RCA": 30.0},
        ]
    )

    indicador_teste = {
        "carregar": lambda: dados,
        "granularidade_periodo": "mensal",
        "campos": {
            "meta_filial": ("META_FILIAL", "sum", {"unico_por": ("FILIAL", "ANO", "MES")}),
            "meta_rca": ("META_RCA", "sum"),
        },
        "dimensoes": {"filial": "FILIAL", "rca": "RCA", "mes": "MES", "ano": "ANO"},
        "unidade": "teste",
    }
    monkeypatch.setitem(catalogo.INDICADORES, "indicador_teste", indicador_teste)

    resultado_sem_agrupar = orq.executar_consulta(
        {"indicador": "indicador_teste", "filtros": {"mes": [7], "ano": [2025]}}
    )
    assert resultado_sem_agrupar["resultados"][0]["meta_filial"] == 100.0
    assert resultado_sem_agrupar["resultados"][0]["meta_rca"] == 100.0

    resultado_por_filial = orq.executar_consulta(
        {
            "indicador": "indicador_teste",
            "filtros": {"mes": [7], "ano": [2025]},
            "agrupar_por": ["filial"],
        }
    )
    item = resultado_por_filial["resultados"][0]
    assert item["meta_filial"] == 100.0
    assert item["meta_rca"] == 100.0

    resultado_por_rca = orq.executar_consulta(
        {
            "indicador": "indicador_teste",
            "filtros": {"mes": [7], "ano": [2025]},
            "agrupar_por": ["rca"],
        }
    )
    por_rca = {item["rca"]: item for item in resultado_por_rca["resultados"]}
    assert por_rca["RCA A"]["meta_filial"] == 100.0
    assert por_rca["RCA A"]["meta_rca"] == 30.0
    assert por_rca["RCA B"]["meta_rca"] == 40.0


def test_executar_consulta_meta_inclui_necessidade_diaria_no_mes_atual(
    monkeypatch,
):
    class DataFalsa(date):
        @classmethod
        def today(cls):
            return date(2026, 8, 26)

    monkeypatch.setattr(motor_metricas, "date", DataFalsa)
    monkeypatch.setitem(
        catalogo.INDICADORES["meta"],
        "carregar",
        lambda: pd.DataFrame(
            [
                {
                    "FILIAL": "TIMON",
                    "COD_RCA": 8403,
                    "COD_SUPERVISOR": 9,
                    "MES": 8,
                    "ANO": 2026,
                    "VENDA_LIQ": 80000.0,
                    "VALOR_META": 100000.0,
                }
            ]
        ),
    )

    resultado = orq.executar_consulta(
        {"indicador": "meta", "filtros": {"mes": [8], "ano": [2026]}}
    )

    assert resultado["resultados"][0]["necessidade_diaria"] == round(
        20000.0 / 4, 2
    )


def test_executar_consulta_meta_sem_necessidade_diaria_fora_do_mes_atual(
    monkeypatch,
):
    class DataFalsa(date):
        @classmethod
        def today(cls):
            return date(2026, 8, 26)

    monkeypatch.setattr(motor_metricas, "date", DataFalsa)
    monkeypatch.setitem(catalogo.INDICADORES["meta"], "carregar", _dados_meta)

    resultado = orq.executar_consulta(
        {"indicador": "meta", "filtros": {"mes": [7], "ano": [2025]}}
    )

    assert "necessidade_diaria" not in resultado["resultados"][0]


def test_executar_consulta_faturamento_ordenar_por_maior_limite_1(monkeypatch):
    monkeypatch.setitem(
        catalogo.INDICADORES["faturamento"], "carregar", _dados_faturamento
    )

    resultado = orq.executar_consulta(
        {
            "indicador": "faturamento",
            "filtros": {"ano": [2025]},
            "ordenar_por": {"campo": "faturamento", "limite": 1},
        }
    )

    assert len(resultado["resultados"]) == 1
    assert resultado["resultados"][0]["faturamento"] == 100.0


def test_executar_consulta_faturamento_ordenar_por_agrupado_top_n(monkeypatch):
    dados = pd.DataFrame(
        [
            {
                "FILIAL": "A", "COD_RCA": 1, "MES": 1, "ANO": 2025,
                "VENDA_LIQ": 50.0, "VENDA_BRUTA": 0, "VALORDESC": 0,
                "PESOLIQ": 0, "QT_NOTAS": 0,
            },
            {
                "FILIAL": "B", "COD_RCA": 2, "MES": 1, "ANO": 2025,
                "VENDA_LIQ": 150.0, "VENDA_BRUTA": 0, "VALORDESC": 0,
                "PESOLIQ": 0, "QT_NOTAS": 0,
            },
            {
                "FILIAL": "C", "COD_RCA": 3, "MES": 1, "ANO": 2025,
                "VENDA_LIQ": 100.0, "VENDA_BRUTA": 0, "VALORDESC": 0,
                "PESOLIQ": 0, "QT_NOTAS": 0,
            },
        ]
    )
    monkeypatch.setitem(
        catalogo.INDICADORES["faturamento"], "carregar", lambda: dados
    )

    resultado = orq.executar_consulta(
        {
            "indicador": "faturamento",
            "filtros": {"ano": [2025]},
            "agrupar_por": ["filial"],
            "ordenar_por": {"campo": "faturamento", "ordem": "desc", "limite": 2},
        }
    )

    assert [item["filial"] for item in resultado["resultados"]] == ["B", "C"]


def test_executar_consulta_ordenar_por_ascendente_menor(monkeypatch):
    monkeypatch.setitem(catalogo.INDICADORES["meta"], "carregar", _dados_meta)

    resultado = orq.executar_consulta(
        {
            "indicador": "meta",
            "filtros": {"mes": [7], "ano": [2025]},
            "agrupar_por": ["filial"],
            "ordenar_por": {
                "campo": "percentual_atingimento",
                "ordem": "asc",
                "limite": 1,
            },
        }
    )

    assert resultado["resultados"][0]["filial"] == "TIMON"


def test_executar_consulta_meta_agrupada_por_supervisor_vira_inteiro(
    monkeypatch,
):
    """
    Regressão: COD_SUPERVISOR vinha formatado como "9.0" em vez de "9"
    (faltava "supervisor" na lista de dimensões convertidas pra int).
    """
    monkeypatch.setitem(catalogo.INDICADORES["meta"], "carregar", _dados_meta)

    resultado = orq.executar_consulta(
        {
            "indicador": "meta",
            "filtros": {"mes": [7], "ano": [2025]},
            "agrupar_por": ["supervisor"],
        }
    )

    supervisores = {item["supervisor"] for item in resultado["resultados"]}
    assert supervisores == {9, 11}
    assert all(isinstance(s, int) for s in supervisores)


def test_executar_consulta_meta_filtros_calculados_atingimento_minimo(
    monkeypatch,
):
    monkeypatch.setitem(catalogo.INDICADORES["meta"], "carregar", _dados_meta)

    resultado = orq.executar_consulta(
        {
            "indicador": "meta",
            "filtros": {"mes": [7], "ano": [2025]},
            "agrupar_por": ["filial"],
            "filtros_calculados": [
                {
                    "campo": "percentual_atingimento",
                    "operador": ">=",
                    "valor": 100,
                }
            ],
        }
    )

    assert len(resultado["resultados"]) == 1
    assert resultado["resultados"][0]["filial"] == "TIBIRI"


# --- campos calculados na comparação, períodos por data, NPS ---


def _dados_nps():
    def linha(filial, dia, nota):
        data = pd.Timestamp(dia)
        return {
            "FILIAL": filial, "DATA": data, "MES": data.month, "ANO": data.year,
            "RESPOSTA": 1, "PROMOTOR": int(nota >= 9),
            "NEUTRO": int(7 <= nota <= 8), "DETRATOR": int(nota <= 6),
        }

    return pd.DataFrame(
        [
            # TIMON 2024: 1 promotor + 1 detrator -> NPS 0
            linha("TIMON", "2024-07-10", 10), linha("TIMON", "2024-07-11", 3),
            # TIMON 2025: 3 promotores + 1 neutro -> NPS 75
            linha("TIMON", "2025-07-01", 10), linha("TIMON", "2025-07-15", 9),
            linha("TIMON", "2025-07-31", 10), linha("TIMON", "2025-08-01", 8),
            # TIBIRI 2024: 1 detrator -> NPS -100; 2025: 1 promotor -> 100
            linha("TIBIRI", "2024-07-10", 2), linha("TIBIRI", "2025-07-10", 10),
        ]
    )


def test_nps_calculado_sobre_a_soma_e_intervalo_inclui_o_ultimo_dia(monkeypatch):
    monkeypatch.setitem(catalogo.INDICADORES["nps"], "carregar", _dados_nps)

    resultado = orq.executar_consulta(
        {
            "indicador": "nps",
            "periodo": "personalizado",
            "periodo_personalizado": {
                "data_inicial": "2025-07-01", "data_final": "2025-07-31",
            },
        }
    )

    item = resultado["resultados"][0]
    # 4 respostas de julho/2025 (a de 31/07 conta; a de 01/08 fica de
    # fora), todas promotoras.
    assert item["total_respostas"] == 4.0
    assert item["total_promotores"] == 4.0
    assert item["nps"] == 100.0
    assert item["percentual_promotores"] == 100.0


def test_comparar_com_compara_tambem_campos_calculados(monkeypatch):
    monkeypatch.setitem(catalogo.INDICADORES["nps"], "carregar", _dados_nps)

    resultado = orq.executar_consulta(
        {
            "indicador": "nps",
            "filtros": {"ano": [2025]},
            "agrupar_por": ["filial"],
            "comparar_com": "ano_anterior_ao_filtro",
            "ordenar_por": {"campo": "diferenca_nps", "ordem": "desc"},
        }
    )

    por_filial = {item["filial"]: item for item in resultado["resultados"]}
    # TIBIRI foi de -100 a 100 (+200); TIMON foi de 0 a 100 (+100).
    assert por_filial["TIBIRI"]["nps_anterior"] == -100.0
    assert por_filial["TIBIRI"]["diferenca_nps"] == 200.0
    assert por_filial["TIMON"]["nps_anterior"] == 0.0
    assert resultado["resultados"][0]["filial"] == "TIBIRI"


def test_nps_variacao_mes_a_mes_usa_o_campo_calculado(monkeypatch):
    monkeypatch.setitem(catalogo.INDICADORES["nps"], "carregar", _dados_nps)

    resultado = orq.executar_consulta(
        {
            "indicador": "nps",
            "filtros": {"ano": [2025]},
            "agrupar_por": ["mes"],
        }
    )

    por_mes = {item["mes"]: item for item in resultado["resultados"]}
    assert por_mes[7]["nps"] == 100.0
    assert por_mes[8]["nps"] == 0.0
    assert por_mes[8]["diferenca_mes_anterior"] == -100.0


def test_comparar_com_personalizado_compara_com_qualquer_periodo(monkeypatch):
    monkeypatch.setitem(
        catalogo.INDICADORES["faturamento"], "carregar", _dados_faturamento
    )

    resultado = orq.executar_consulta(
        {
            "indicador": "faturamento",
            "filtros": {"ano": [2025]},
            "comparar_com": "personalizado",
            "comparar_com_personalizado": {"anos": [2024]},
        }
    )

    item = resultado["resultados"][0]
    assert item["faturamento_anterior"] == 80.0
    assert item["percentual_faturamento"] == 25.0


def _com_data_fixa(monkeypatch):
    class DataFalsa(date):
        @classmethod
        def today(cls):
            return date(2026, 1, 15)

    monkeypatch.setattr(orq, "date", DataFalsa)


def test_periodos_por_data_aceitam_mes_anterior_e_mesmo_mes_ano_anterior(
    monkeypatch,
):
    _com_data_fixa(monkeypatch)

    assert orq.resolver_periodo("mes_anterior", None, "diaria") == {
        "dia": {"data_inicial": "2025-12-01", "data_final": "2025-12-31"}
    }
    assert orq.resolver_periodo("mesmo_mes_ano_anterior", None, "diaria") == {
        "dia": {"data_inicial": "2025-01-01", "data_final": "2025-01-31"}
    }


def test_periodo_personalizado_por_data_aceita_meses_e_anos():
    assert orq.resolver_periodo(
        "personalizado", {"meses": [7], "anos": [2025]}, "diaria"
    ) == {"mes": [7], "ano": [2025]}


def test_periodo_incompativel_com_o_indicador_nao_e_ignorado_em_silencio():
    # faturamento_diario não tem dimensão "mes"/"ano".
    with pytest.raises(ConsultaInvalida):
        orq.executar_consulta(
            {
                "indicador": "faturamento_diario",
                "periodo": "personalizado",
                "periodo_personalizado": {"meses": [7], "anos": [2025]},
            }
        )


def test_contagens_continuam_inteiras_no_resultado(monkeypatch):
    monkeypatch.setitem(catalogo.INDICADORES["nps"], "carregar", _dados_nps)

    total = orq.executar_consulta({"indicador": "nps"})["resultados"][0]
    por_filial = orq.executar_consulta(
        {"indicador": "nps", "agrupar_por": ["filial"]}
    )["resultados"]

    assert isinstance(total["total_respostas"], int)
    assert total["total_respostas"] == 8
    assert all(isinstance(i["total_promotores"], int) for i in por_filial)
    # Valores que não são contagem (o NPS) seguem com casas decimais.
    assert isinstance(total["nps"], float)


def test_variacao_mes_a_mes_funciona_com_periodo_personalizado(monkeypatch):
    """
    Regressão: a variação em relação ao mesmo mês do ano anterior só
    era calculada quando o(s) ano(s) vinham em "filtros" — se vinham
    por "periodo_personalizado", ela sumia em silêncio.
    """
    monkeypatch.setitem(catalogo.INDICADORES["nps"], "carregar", _dados_nps)

    resultado = orq.executar_consulta(
        {
            "indicador": "nps",
            "agrupar_por": ["mes", "ano"],
            "periodo": "personalizado",
            "periodo_personalizado": {"meses": [7], "anos": [2024, 2025]},
        }
    )

    por_ano = {item["ano"]: item for item in resultado["resultados"]}
    # julho/2024: 1 promotor e 2 detratores em 3 respostas (NPS -33,33);
    # julho/2025: 4 promotores em 4 respostas (NPS 100).
    assert por_ano[2024]["diferenca_ano_anterior"] is None
    assert por_ano[2025]["nps_ano_anterior"] == -33.33
    assert por_ano[2025]["diferenca_ano_anterior"] == 133.33


def test_necessidade_diaria_funciona_quando_o_mes_vem_pelo_periodo(monkeypatch):
    class DataFalsa(date):
        @classmethod
        def today(cls):
            return date(2026, 8, 26)

    monkeypatch.setattr(orq, "date", DataFalsa)
    monkeypatch.setattr(motor_metricas, "date", DataFalsa)
    monkeypatch.setitem(
        catalogo.INDICADORES["meta"],
        "carregar",
        lambda: pd.DataFrame(
            [
                {
                    "FILIAL": "TIMON", "COD_RCA": 8403,
                    "COD_SUPERVISOR": 9, "MES": 8, "ANO": 2026,
                    "VENDA_LIQ": 80000.0, "VALOR_META": 100000.0,
                }
            ]
        ),
    )

    resultado = orq.executar_consulta(
        {"indicador": "meta", "periodo": "mes_atual"}
    )

    assert resultado["resultados"][0]["necessidade_diaria"] == 5000.0


def test_agrupado_por_filial_traz_o_codigo_de_cada_filial(monkeypatch):
    """Sem o código no resultado, a IA adivinha o código pelo nome e erra."""
    dados = pd.DataFrame(
        [
            {"FILIAL": "GUAJAJARAS", "MES": 7, "ANO": 2025, "VENDA_LIQ": 74.0,
             "VENDA_BRUTA": 0, "VALORDESC": 0, "PESOLIQ": 0, "QT_NOTAS": 0},
            {"FILIAL": "AREINHA", "MES": 7, "ANO": 2025, "VENDA_LIQ": 44.0,
             "VENDA_BRUTA": 0, "VALORDESC": 0, "PESOLIQ": 0, "QT_NOTAS": 0},
        ]
    )
    monkeypatch.setitem(catalogo.INDICADORES["faturamento"], "carregar", lambda: dados)

    resultado = orq.executar_consulta(
        {
            "indicador": "faturamento",
            "filtros": {"filial": ["5", "6"], "ano": [2025]},
            "agrupar_por": ["filial"],
        }
    )

    codigos = {item["filial"]: item["codigo_filial"] for item in resultado["resultados"]}
    assert codigos == {"GUAJAJARAS": 5, "AREINHA": 6}


def _faturamento_dois_anos():
    def linha(filial, ano, valor):
        return {
            "FILIAL": filial, "MES": 7, "ANO": ano, "VENDA_LIQ": valor,
            "VENDA_BRUTA": valor, "VALORDESC": 0.0, "PESOLIQ": 1000.0,
            "QT_NOTAS": 1,
        }

    return pd.DataFrame(
        [
            linha("TIMON", 2024, 100.0), linha("TIMON", 2025, 150.0),
            linha("PICOS", 2024, 80.0), linha("PICOS", 2025, 72.0),
        ]
    )


def test_agrupar_por_filial_e_ano_traz_a_variacao_em_relacao_ao_ano_anterior(monkeypatch):
    """Antes só havia variação entre anos quando o mês também era agrupado."""
    monkeypatch.setitem(catalogo.INDICADORES["faturamento"], "carregar", _faturamento_dois_anos)

    resultado = orq.executar_consulta(
        {
            "indicador": "faturamento",
            "filtros": {"ano": [2024, 2025]},
            "agrupar_por": ["filial", "ano"],
        }
    )

    por_chave = {(i["filial"], i["ano"]): i for i in resultado["resultados"]}

    assert por_chave[("TIMON", 2024)]["percentual_ano_anterior"] is None
    assert por_chave[("TIMON", 2025)]["percentual_ano_anterior"] == 50.0
    assert por_chave[("PICOS", 2025)]["percentual_ano_anterior"] == -10.0


def test_colunas_devolve_a_tabela_recortada_e_o_resultado_completo(monkeypatch):
    monkeypatch.setitem(catalogo.INDICADORES["faturamento"], "carregar", _faturamento_dois_anos)

    resultado = orq.executar_consulta(
        {
            "indicador": "faturamento",
            "filtros": {"ano": [2025]},
            "agrupar_por": ["filial"],
            "colunas": ["faturamento"],
        }
    )

    linha_completa = resultado["resultados"][0]
    linha_tabela = resultado["tabela"][0]

    assert "venda_bruta" in linha_completa  # a IA recebe tudo
    assert set(linha_tabela) == {"filial", "faturamento", "_colunas_pedidas"}


def test_sem_colunas_nao_devolve_tabela_recortada(monkeypatch):
    monkeypatch.setitem(catalogo.INDICADORES["faturamento"], "carregar", _faturamento_dois_anos)

    resultado = orq.executar_consulta(
        {"indicador": "faturamento", "filtros": {"ano": [2025]}, "agrupar_por": ["filial"]}
    )

    assert "tabela" not in resultado


def test_colunas_com_campo_inexistente_gera_erro_claro():
    with pytest.raises(ConsultaInvalida):
        orq.executar_consulta(
            {"indicador": "faturamento", "colunas": ["campo_que_nao_existe"]}
        )
