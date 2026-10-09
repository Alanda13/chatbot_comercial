from datetime import date

import pandas as pd
import pytest

from core.motor import catalogo
from core.motor import motor_metricas
from core.motor import orquestrador as orq
from core.exceptions import ConsultaInvalida


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
            {"indicador": "meta", "agrupar_por": ["produto"]}
        )


def test_validar_consulta_rejeita_filtro_fora_do_catalogo():
    with pytest.raises(ConsultaInvalida):
        orq.validar_consulta(
            {"indicador": "meta", "filtros": {"produto": ["X"]}}
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
        orq.executar_consulta({"indicador": "inadimplencia"})


# --- executar_consulta: desconto ---


def _dados_desconto():
    return pd.DataFrame(
        [
            {
                "FILIAL": "TIMON", "COD_RCA": 8403, "COD_SUPERVISOR": 9,
                "MES": 8, "ANO": 2026,
                "VALORDESC": 30.0, "VENDA_TABELA": 1000.0, "VENDA_BRUTA": 1000.0,
            },
            {
                "FILIAL": "CAXIAS", "COD_RCA": 8500, "COD_SUPERVISOR": 9,
                "MES": 8, "ANO": 2026,
                "VALORDESC": 10.0, "VENDA_TABELA": 1000.0, "VENDA_BRUTA": 1000.0,
            },
        ]
    )


def test_executar_consulta_desconto_calcula_percentual_sobre_as_somas(monkeypatch):
    monkeypatch.setitem(catalogo.INDICADORES["desconto"], "carregar", _dados_desconto)

    resultado = orq.executar_consulta(
        {"indicador": "desconto", "filtros": {"mes": [8], "ano": [2026]}}
    )

    # (30 + 10) / (1000 + 1000) = 2% — e não a média de 3% e 1%.
    assert resultado["resultados"] == [
        {
            "valor_desconto": 40.0,
            "faturamento_tabela": 2000.0,
            "venda_bruta": 2000.0,
            "percentual_desconto": 2.0,
        }
    ]


def test_executar_consulta_desconto_agrupado_por_filial(monkeypatch):
    monkeypatch.setitem(catalogo.INDICADORES["desconto"], "carregar", _dados_desconto)

    resultado = orq.executar_consulta(
        {
            "indicador": "desconto",
            "filtros": {"mes": [8], "ano": [2026]},
            "agrupar_por": ["filial"],
        }
    )

    por_filial = {
        linha["filial"]: linha["percentual_desconto"]
        for linha in resultado["resultados"]
    }
    assert por_filial == {"TIMON": 3.0, "CAXIAS": 1.0}


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


def test_periodo_ano_anterior(monkeypatch):
    _com_data_fixa(monkeypatch)

    assert orq.resolver_periodo("ano_anterior", None, "mensal") == {"ano": [2025]}
    assert orq.resolver_periodo("ano_anterior", None, "diaria") == {
        "dia": {"data_inicial": "2025-01-01", "data_final": "2025-12-31"}
    }


def test_periodo_semana_anterior_vai_de_segunda_a_domingo(monkeypatch):
    _com_data_fixa(monkeypatch)  # 15/01/2026, quinta-feira

    assert orq.resolver_periodo("semana_anterior", None, "diaria") == {
        "dia": {"data_inicial": "2026-01-05", "data_final": "2026-01-11"}
    }


def test_periodo_semana_anterior_nao_existe_em_indicador_mensal(monkeypatch):
    _com_data_fixa(monkeypatch)

    with pytest.raises(ConsultaInvalida):
        orq.resolver_periodo("semana_anterior", None, "mensal")


def test_descrever_periodo():
    assert orq._descrever_periodo({"mes": [9], "ano": [2026]})["descricao"] == (
        "setembro de 2026"
    )
    assert orq._descrever_periodo({"mes": [7, 8], "ano": [2025]})["descricao"] == (
        "julho e agosto de 2025"
    )
    assert orq._descrever_periodo({"ano": [2025, 2026]})["descricao"] == "2025 e 2026"
    assert orq._descrever_periodo(
        {"dia": {"data_inicial": "2026-09-30", "data_final": "2026-09-30"}}
    )["descricao"] == "30/09/2026"
    assert orq._descrever_periodo(
        {"dia": {"data_inicial": "2026-09-01", "data_final": "2026-09-30"}}
    )["descricao"] == "de 01/09/2026 a 30/09/2026"
    assert orq._descrever_periodo({"filial": ["TIMON"]}) is None


def test_resultado_informa_o_periodo_consultado_e_o_comparado(monkeypatch):
    class DataFalsa(date):
        @classmethod
        def today(cls):
            return date(2026, 10, 1)

    monkeypatch.setattr(orq, "date", DataFalsa)
    monkeypatch.setitem(catalogo.INDICADORES["desconto"], "carregar", _dados_desconto)

    resultado = orq.executar_consulta(
        {
            "indicador": "desconto",
            "periodo": "mes_anterior",
            "comparar_com": "personalizado",
            "comparar_com_personalizado": {"meses": [8], "anos": [2026]},
        }
    )

    # "mês passado" em 01/10/2026 é SETEMBRO — vai escrito no resultado
    # pra IA não deduzir o mês sozinha.
    assert resultado["periodo_consultado"]["descricao"] == "setembro de 2026"
    assert resultado["periodo_comparado"]["descricao"] == "agosto de 2026"


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


def test_rca_com_meta_zero_numa_filial_nao_vaza_de_outra_filial_onde_tem_meta(
    monkeypatch,
):
    """
    Regressão: código genérico (ex: conta "MATRIZ") reaproveitado em
    várias filiais, com meta de verdade só numa delas. Antes, quando a
    consulta trazia várias filiais de uma vez (sem filtro de filial), a
    validade do código era calculada somando a meta dele em TODAS as
    filiais juntas — a meta de uma única filial "vazava" e o código
    aparecia como RCA válido também nas filiais onde não tinha meta
    nenhuma.
    """
    dados_faturamento_teste = pd.DataFrame(
        [
            {
                "FILIAL": "CAMPOS SALES", "COD_RCA": 1, "MES": 7,
                "ANO": 2025, "VENDA_LIQ": 100.0, "VENDA_BRUTA": 0,
                "VALORDESC": 0, "PESOLIQ": 0, "QT_NOTAS": 0,
            },
            {
                "FILIAL": "TIMON", "COD_RCA": 1, "MES": 7,
                "ANO": 2025, "VENDA_LIQ": 30.0, "VENDA_BRUTA": 0,
                "VALORDESC": 0, "PESOLIQ": 0, "QT_NOTAS": 0,
            },
            {
                "FILIAL": "TIMON", "COD_RCA": 8403, "MES": 7,
                "ANO": 2025, "VENDA_LIQ": 50.0, "VENDA_BRUTA": 0,
                "VALORDESC": 0, "PESOLIQ": 0, "QT_NOTAS": 0,
            },
        ]
    )
    dados_meta_teste = pd.DataFrame(
        [
            # código 1 é conta genérica: tem meta em Campos Sales,
            # mas zero em Timon.
            {
                "FILIAL": "CAMPOS SALES", "COD_RCA": 1, "MES": 7,
                "ANO": 2025, "VENDA_LIQ": 100.0, "VALOR_META": 90.0,
            },
            {
                "FILIAL": "TIMON", "COD_RCA": 1, "MES": 7,
                "ANO": 2025, "VENDA_LIQ": 30.0, "VALOR_META": 0.0,
            },
            {
                "FILIAL": "TIMON", "COD_RCA": 8403, "MES": 7,
                "ANO": 2025, "VENDA_LIQ": 50.0, "VALOR_META": 40.0,
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
            "filtros": {"mes": [7], "ano": [2025]},
            "agrupar_por": ["filial", "rca"],
        }
    )

    por_filial = {}
    for item in resultado["resultados"]:
        por_filial.setdefault(item["filial"], []).append(item["rca"])

    assert por_filial["CAMPOS SALES"] == [1]
    assert por_filial["TIMON"] == [8403]  # o código 1 NÃO aparece aqui


# --- correções de 05/10/2026 (teste de faturamento) ---

def test_agrupado_por_2_anos_ignora_comparar_com(monkeypatch):
    """
    Agrupada por ano (2024 e 2025), a consulta já traz a variação ano a
    ano; um "comparar_com" a mais comparava cada ano com ele mesmo
    (2024 x 2024 = +0,00%, 2025 "sem dados").
    """
    monkeypatch.setitem(catalogo.INDICADORES["faturamento"], "carregar", _dados_faturamento)

    resultado = orq.executar_consulta({
        "indicador": "faturamento",
        "filtros": {"ano": [2024, 2025]},
        "agrupar_por": ["ano"],
        "comparar_com": "ano_anterior_ao_filtro",
    })["resultados"]

    assert [(linha["ano"], linha.get("faturamento_anterior")) for linha in resultado] == [
        (2024, None), (2025, None),
    ]
    assert resultado[1]["percentual_ano_anterior"] == 25.0


def test_comparacao_com_periodo_principal_sem_venda_mostra_o_outro(monkeypatch):
    """10/08/2025 (domingo, sem venda) x 20/08/2025: antes sumia tudo."""
    dados = pd.DataFrame([
        {"FILIAL": "TIMON", "DATA": pd.Timestamp("2025-08-20"), "VENDA_LIQ": 100.0,
         "VENDA_BRUTA": 110.0, "VALORDESC": 1.0, "QT_NOTAS": 3, "COD_RCA": 1},
    ])
    monkeypatch.setitem(catalogo.INDICADORES["faturamento_diario"], "carregar", lambda: dados)

    resposta = orq.executar_consulta({
        "indicador": "faturamento_diario",
        "periodo": "personalizado",
        "periodo_personalizado": {"data_inicial": "2025-08-10", "data_final": "2025-08-10"},
        "comparar_com": "personalizado",
        "comparar_com_personalizado": {"data_inicial": "2025-08-20", "data_final": "2025-08-20"},
    })

    assert resposta["encontrado"] is True
    assert resposta["resultados"][0]["faturamento"] is None
    assert resposta["resultados"][0]["faturamento_anterior"] == 100.0


def test_agrupar_por_supervisor_traz_o_nome(monkeypatch):
    dados = _dados_meta().assign(NOME_SUPERVISOR=["SUPERVISOR TIMON", "SUPERVISOR TIBIRI"][: len(_dados_meta())])
    monkeypatch.setitem(catalogo.INDICADORES["meta"], "carregar", lambda: dados)

    resultado = orq.executar_consulta({
        "indicador": "meta", "filtros": {"ano": [2025]}, "agrupar_por": ["supervisor"],
    })["resultados"]

    assert {linha["supervisor"]: linha["supervisor_nome"] for linha in resultado}[9] == "SUPERVISOR TIMON"


def test_desconto_diario_por_rca_na_semana(monkeypatch):
    """'Qual RCA mais concedeu desconto semana passada?' — o desconto
    mensal recusava; o diário responde com R$ e % (sobre as somas)."""
    dados = pd.DataFrame([
        {"FILIAL": "TIMON", "ESTADO": "MA", "COD_RCA": 1, "DATA": pd.Timestamp(dia),
         "VALORDESC": desconto, "VENDA_TABELA": tabela, "VENDA_BRUTA": tabela}
        for dia, desconto, tabela in [
            ("2026-09-28", 10.0, 100.0), ("2026-09-29", 30.0, 100.0), ("2026-09-20", 99.0, 100.0),
        ]
    ])
    monkeypatch.setitem(catalogo.INDICADORES["desconto_diario"], "carregar", lambda: dados)
    monkeypatch.setitem(catalogo.INDICADORES["desconto_diario"], "rca_requer_meta_cadastrada", False)

    resposta = orq.executar_consulta({
        "indicador": "desconto_diario",
        "periodo": "personalizado",
        "periodo_personalizado": {"data_inicial": "2026-09-28", "data_final": "2026-10-04"},
        "agrupar_por": ["rca"],
    })

    linha = resposta["resultados"][0]
    assert (linha["valor_desconto"], linha["percentual_desconto"]) == (40.0, 20.0)


def test_desconto_diario_sem_periodo_usa_do_comeco_do_ano_ate_hoje(monkeypatch):
    dados = pd.DataFrame([
        {"FILIAL": "TIMON", "ESTADO": "MA", "COD_RCA": 1, "DATA": pd.Timestamp(dia),
         "VALORDESC": 10.0, "VENDA_TABELA": 100.0, "VENDA_BRUTA": 100.0}
        for dia in ("2025-12-31", "2026-01-02", "2026-10-02")
    ])
    monkeypatch.setattr(orq, "date", _Hoje5DeOutubro)
    monkeypatch.setitem(catalogo.INDICADORES["desconto_diario"], "carregar", lambda: dados)

    resposta = orq.executar_consulta({"indicador": "desconto_diario"})

    assert resposta["periodo_consultado"]["descricao"] == "de 01/01/2026 a 05/10/2026"
    assert "periodo_assumido" in resposta
    assert resposta["resultados"][0]["valor_desconto"] == 20.0


class _Hoje5DeOutubro(date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 5)


def _meta_set_out_2026():
    return pd.DataFrame([
        {"FILIAL": "TIMON", "COD_RCA": 8403, "COD_SUPERVISOR": 9, "MES": mes, "ANO": 2026,
         "VENDA_LIQ": venda, "VALOR_META": meta}
        for mes, venda, meta in [(9, 100.0, 100.0), (10, 8.0, 100.0)]
    ])


def test_acumulado_do_ano_usa_so_meses_fechados(monkeypatch):
    """
    Em 05/10, "atingimento de 2026" somava a meta de outubro inteira contra
    5 dias de venda (Timon: 97,0% até setembro virava 86,1%). O acumulado
    usa só os meses fechados e o mês em andamento vem à parte.
    """
    monkeypatch.setattr(orq, "date", _Hoje5DeOutubro)
    monkeypatch.setitem(catalogo.INDICADORES["meta"], "carregar", _meta_set_out_2026)

    resposta = orq.executar_consulta({"indicador": "meta", "filtros": {"ano": [2026]}})

    assert resposta["periodo_consultado"]["descricao"] == "de janeiro a setembro de 2026"
    assert resposta["resultados"][0]["percentual_atingimento"] == 100.0
    andamento = resposta["mes_em_andamento"]
    assert andamento["descricao"].startswith("outubro de 2026")
    assert andamento["resultados"][0]["percentual_atingimento"] == 8.0


def test_mes_pedido_ou_mes_a_mes_nao_separa(monkeypatch):
    monkeypatch.setattr(orq, "date", _Hoje5DeOutubro)
    monkeypatch.setitem(catalogo.INDICADORES["meta"], "carregar", _meta_set_out_2026)

    este_mes = orq.executar_consulta({"indicador": "meta", "filtros": {"ano": [2026], "mes": [10]}})
    mes_a_mes = orq.executar_consulta(
        {"indicador": "meta", "filtros": {"ano": [2026]}, "agrupar_por": ["mes"]}
    )

    assert "mes_em_andamento" not in este_mes
    assert este_mes["resultados"][0]["percentual_atingimento"] == 8.0
    assert "mes_em_andamento" not in mes_a_mes
    assert [linha["mes"] for linha in mes_a_mes["resultados"]] == [9, 10]


def test_menos_desconto_separa_quem_nao_deu_e_mantem_o_total(monkeypatch):
    """
    'Quem menos deu desconto na sexta' respondia um RCA com R$ 0,00 — ou
    com centavos de arredondamento (meio centavo por item em kg). Abaixo
    de R$ 1,00 sai da lista e vem em "fora_da_lista_de_menor"; o total segue somando
    tudo (igual ao WinThor).
    """
    dados = pd.DataFrame([
        {"FILIAL": "TIMON", "ESTADO": "MA", "COD_RCA": codigo, "DATA": pd.Timestamp("2026-10-02"),
         "VALORDESC": desconto, "VENDA_TABELA": 1000.0, "VENDA_BRUTA": 1000.0}
        for codigo, desconto in [(1, 0.0), (2, 0.07), (3, 17.89), (4, 50.0)]
    ])
    monkeypatch.setitem(catalogo.INDICADORES["desconto_diario"], "carregar", lambda: dados)
    monkeypatch.setitem(catalogo.INDICADORES["desconto_diario"], "rca_requer_meta_cadastrada", False)
    monkeypatch.setitem(catalogo.INDICADORES["desconto_diario"], "rca_nome_mapa", None)

    resposta = orq.executar_consulta({
        "indicador": "desconto_diario",
        "periodo": "personalizado",
        "periodo_personalizado": {"data_inicial": "2026-10-02", "data_final": "2026-10-02"},
        "agrupar_por": ["rca"],
        "ordenar_por": {"campo": "percentual_desconto", "ordem": "asc", "limite": 1},
    })

    assert [linha["rca"] for linha in resposta["resultados"]] == [3]
    assert resposta["fora_da_lista_de_menor"]["quantidade"] == 2
    assert resposta["total_de_todas_as_linhas"]["valor_desconto"] == 67.96


def test_mais_desconto_nao_separa(monkeypatch):
    dados = pd.DataFrame([
        {"FILIAL": "TIMON", "ESTADO": "MA", "COD_RCA": codigo, "DATA": pd.Timestamp("2026-10-02"),
         "VALORDESC": desconto, "VENDA_TABELA": 1000.0, "VENDA_BRUTA": 1000.0}
        for codigo, desconto in [(1, 0.0), (4, 50.0)]
    ])
    monkeypatch.setitem(catalogo.INDICADORES["desconto_diario"], "carregar", lambda: dados)
    monkeypatch.setitem(catalogo.INDICADORES["desconto_diario"], "rca_requer_meta_cadastrada", False)

    resposta = orq.executar_consulta({
        "indicador": "desconto_diario",
        "periodo": "personalizado",
        "periodo_personalizado": {"data_inicial": "2026-10-02", "data_final": "2026-10-02"},
        "agrupar_por": ["rca"],
        "ordenar_por": {"campo": "valor_desconto"},
    })

    assert "fora_da_lista_de_menor" not in resposta
    assert len(resposta["resultados"]) == 2


def test_periodo_padrao_vale_tambem_pro_indicador_cruzado(monkeypatch):
    """Faturamento (sem período padrão) cruzado com desconto: sem período,
    somava o desconto desde 2020 — agora usa o ano atual e avisa."""

    class Hoje(date):
        @classmethod
        def today(cls):
            return cls(2025, 10, 6)

    monkeypatch.setattr(orq, "date", Hoje)
    def base_mensal():
        return _dados_faturamento().assign(VENDA_TABELA=1000.0, ESTADO="MA")

    # Mesma base nos dois (como o faturamento_mensal.csv real).
    monkeypatch.setitem(catalogo.INDICADORES["faturamento"], "carregar", base_mensal)
    monkeypatch.setitem(catalogo.INDICADORES["desconto"], "carregar", base_mensal)

    resposta = orq.executar_consulta({
        "indicador": "faturamento", "cruzar_com": ["desconto"], "agrupar_por": ["filial"],
    })

    assert resposta["periodo_consultado"]["descricao"] == "2025"
    assert "periodo_assumido" in resposta
    assert resposta["resultados"][0]["faturamento"] == 100.0


def test_tabela_mostra_so_os_campos_da_ordem_e_dos_filtros(monkeypatch):
    """'RCAs com mais desconto que não bateram a meta' saía com 7 colunas
    (até "Faturamento de Tabela"): sem "colunas" da IA, só os campos
    usados na ordem e nos filtros."""
    monkeypatch.setitem(catalogo.INDICADORES["desconto"], "carregar", _dados_desconto)

    resposta = orq.executar_consulta({
        "indicador": "desconto", "filtros": {"mes": [8], "ano": [2026]}, "agrupar_por": ["filial"],
        "filtros_calculados": [{"campo": "valor_desconto", "operador": ">", "valor": 0}],
        "ordenar_por": {"campo": "percentual_desconto"},
    })

    assert resposta["tabela"][0]["_colunas_pedidas"] == ["percentual_desconto", "valor_desconto"]


def test_comparar_ano_atual_usa_os_mesmos_meses_nos_dois_anos(monkeypatch):
    """Em 05/10/2026, 2026 (9 meses) x 2025 (12) dava quase toda filial
    caindo. Agora os dois anos usam jan-set."""
    dados = pd.DataFrame([
        {"FILIAL": "TIMON", "ESTADO": "MA", "COD_RCA": 1, "ANO": ano, "MES": mes,
         "VENDA_LIQ": 100.0, "VENDA_BRUTA": 100.0, "VALORDESC": 0.0, "PESOLIQ": 0.0, "QT_NOTAS": 1}
        for ano in (2025, 2026) for mes in range(1, 13) if not (ano == 2026 and mes > 10)
    ])
    monkeypatch.setattr(orq, "date", _Hoje5DeOutubro)
    monkeypatch.setitem(catalogo.INDICADORES["faturamento"], "carregar", lambda: dados)

    resposta = orq.executar_consulta({
        "indicador": "faturamento", "filtros": {"ano": [2025, 2026]}, "agrupar_por": ["ano"],
    })

    assert resposta["periodo_consultado"]["descricao"] == "de janeiro a setembro de 2025 e 2026"
    assert "mesmo_periodo_nos_anos" in resposta
    assert [linha["faturamento"] for linha in resposta["resultados"]] == [900.0, 900.0]


def test_cruzamento_mostra_o_campo_que_resume_cada_indicador(monkeypatch):
    """'NPS e atingimento por filial' ordenado pelo NPS saía só com o NPS."""
    consulta = {"indicador": "nps", "cruzar_com": ["meta"], "ordenar_por": {"campo": "nps"}}

    assert orq._colunas_usadas_na_pergunta(consulta, catalogo.INDICADORES["nps"]) == [
        "nps", "percentual_atingimento",
    ]


def test_tabela_escolhida_pelo_sistema_compara_so_o_campo_da_pergunta(monkeypatch):
    """'Quem mais cresceu deu mais desconto?' saía com 9 colunas: cada campo
    ganhava anterior/diferença/variação. Só o foco da pergunta é comparado."""
    linhas = orq._linhas_da_tabela(
        [{"filial": "TIMON", "faturamento": 100.0, "faturamento_anterior": 90.0,
          "percentual_faturamento": 11.1, "percentual_desconto": 3.0,
          "percentual_desconto_anterior": 2.0, "diferenca_percentual_desconto": 1.0}],
        ["percentual_faturamento", "faturamento", "percentual_desconto"],
        comparar=["percentual_faturamento"],
    )

    assert set(linhas[0]) == {
        "filial", "percentual_faturamento", "faturamento", "percentual_desconto",
        "_colunas_pedidas",
    }


def test_comparacao_de_periodos_tem_titulos_com_o_periodo():
    colunas, rotulos = orq._colunas_da_comparacao_de_periodos(
        ["diferenca_faturamento", "percentual_desconto"],
        ["faturamento", "desconto"], "jan-set/2026", "jan-set/2025",
    )

    assert colunas == [
        "faturamento_anterior", "faturamento", "diferenca_faturamento", "percentual_desconto",
    ]
    assert rotulos["faturamento_anterior"] == "Faturamento jan-set/2025"
    assert rotulos["faturamento"] == "Faturamento jan-set/2026"
    assert rotulos["diferenca_faturamento"] == "Cresceu/caiu (R$)"
    assert rotulos["percentual_desconto"] == "% Desconto (jan-set/2026)"
    assert orq._periodo_curto({"ano": [2026], "mes": [1, 2, 3, 4, 5, 6, 7, 8, 9]}) == "jan-set/2026"


def test_cruza_por_dimensao_que_todos_identificam_igual_e_recusa_a_que_falta():
    orq._validar_cruzamento(["desconto", "faturamento"], ["grupo"])
    orq._validar_cruzamento(["desconto", "faturamento"], ["empresa"])

    with pytest.raises(ConsultaInvalida):
        orq._validar_cruzamento(["meta", "desconto"], ["grupo"])


def test_lista_cortada_pra_ia_fica_com_os_maiores_e_a_tabela_acompanha():
    from core.services.chatbot_service import LIMITE_RESULTADOS_RESPOSTA, _limitar_resultados

    linhas = [{"familia": f"F{i:03d}", "valor_desconto": float(i)} for i in range(100)]
    resultado = {
        "indicador": "desconto", "agrupar_por": ["familia"],
        "resultados": linhas, "tabela": [{"Família": l["familia"]} for l in linhas],
    }

    cortado = _limitar_resultados(resultado)

    assert len(cortado["resultados"]) == LIMITE_RESULTADOS_RESPOSTA
    assert cortado["resultados"][0]["familia"] == "F099"
    assert cortado["tabela"][0] == {"Família": "F099"}
    assert "maiores" in cortado["aviso"]


def test_mes_a_mes_cortado_continua_em_ordem():
    from core.services.chatbot_service import _limitar_resultados

    linhas = [{"mes": m, "valor_desconto": float(100 - m)} for m in range(1, 80)]
    cortado = _limitar_resultados({"indicador": "desconto", "agrupar_por": ["mes"], "resultados": linhas})

    assert cortado["resultados"][0]["mes"] == 1


def test_sem_ninguem_no_filtro_mostra_quem_chegou_mais_perto(monkeypatch):
    dados = pd.DataFrame([
        {"FILIAL": "TIMON", "COD_RCA": 1, "COD_SUPERVISOR": 9, "MES": 8, "ANO": 2026,
         "VALORDESC": 30.0, "VENDA_TABELA": 1000.0, "VENDA_BRUTA": 1000.0},
        {"FILIAL": "CAXIAS", "COD_RCA": 2, "COD_SUPERVISOR": 9, "MES": 8, "ANO": 2026,
         "VALORDESC": 5.0, "VENDA_TABELA": 1000.0, "VENDA_BRUTA": 1000.0},
    ])
    monkeypatch.setitem(catalogo.INDICADORES["desconto"], "carregar", lambda: dados)

    resposta = orq.executar_consulta({
        "indicador": "desconto", "filtros": {"ano": [2026]}, "agrupar_por": ["filial"],
        "filtros_calculados": [
            {"campo": "valor_desconto", "operador": ">", "valor": 10},
            {"campo": "percentual_desconto", "operador": ">", "valor": 5},
        ],
    })

    assert resposta["resultados"] == []
    perto = resposta["mais_perto_do_filtro"]["itens"]
    assert [item["filial"] for item in perto] == ["TIMON"]
    assert perto[0]["condicao_que_faltou"] == "percentual_desconto > 5"


def test_menos_faturou_separa_rca_que_so_tem_meta(monkeypatch):
    """
    'Os 5 RCAs que menos faturaram' vinha com 3 RCAs de R$ 0,00 — só
    tinham meta cadastrada, não venderam nada. Saem da lista e vêm à
    parte; o total segue somando tudo. Cruzado com desconto, a tabela
    mostra o desconto em R$ e em %.
    """
    dados = pd.DataFrame([
        {"FILIAL": "TIMON", "ESTADO": "MA", "COD_RCA": codigo, "ANO": 2026, "MES": 1,
         "VENDA_BRUTA": venda, "VENDA_LIQ": venda, "VALORDESC": venda * 0.01,
         "VENDA_TABELA": venda * 1.01, "PESOLIQ": 0.0, "QT_NOTAS": 1, "VALOR_META": 100.0}
        for codigo, venda in [(1, 0.0), (2, 500.0), (3, 900.0)]
    ])
    # Mesma função nos dois: campos com o mesmo nome vêm do mesmo arquivo.
    carregar = lambda: dados  # noqa: E731
    for nome in ("faturamento", "desconto"):
        monkeypatch.setitem(catalogo.INDICADORES[nome], "carregar", carregar)
        monkeypatch.setitem(catalogo.INDICADORES[nome], "rca_requer_meta_cadastrada", False)
        monkeypatch.setitem(catalogo.INDICADORES[nome], "rca_nome_mapa", None)

    resposta = orq.executar_consulta({
        "indicador": "faturamento",
        "cruzar_com": ["desconto"],
        "filtros": {"ano": [2026]},
        "agrupar_por": ["rca"],
        "ordenar_por": {"campo": "faturamento", "ordem": "asc", "limite": 5},
    })

    assert [linha["rca"] for linha in resposta["resultados"]] == [2, 3]
    assert resposta["fora_da_lista_de_menor"]["quantidade"] == 1
    assert "não venderam nada" in resposta["fora_da_lista_de_menor"]["motivo"]
    assert resposta["tabela"][0]["_colunas_pedidas"] == ["faturamento", "valor_desconto", "percentual_desconto"]


def test_menos_faturou_nao_separa_por_falta_de_desconto(monkeypatch):
    """A regra é do campo ORDENADO: 'quem menos faturou' não tira quem não
    deu desconto (antes a regra do desconto valia pra qualquer ordem)."""
    dados = pd.DataFrame([
        {"FILIAL": "TIMON", "ESTADO": "MA", "COD_RCA": codigo, "ANO": 2026, "MES": 1,
         "VENDA_BRUTA": 500.0, "VENDA_LIQ": 500.0, "VALORDESC": desconto,
         "VENDA_TABELA": 500.0, "PESOLIQ": 0.0, "QT_NOTAS": 1, "VALOR_META": 100.0}
        for codigo, desconto in [(1, 0.0), (2, 30.0)]
    ])
    monkeypatch.setitem(catalogo.INDICADORES["desconto"], "carregar", lambda: dados)
    monkeypatch.setitem(catalogo.INDICADORES["desconto"], "rca_requer_meta_cadastrada", False)
    monkeypatch.setitem(catalogo.INDICADORES["desconto"], "rca_nome_mapa", None)

    resposta = orq.executar_consulta({
        "indicador": "desconto",
        "filtros": {"ano": [2026]},
        "agrupar_por": ["rca"],
        "ordenar_por": {"campo": "venda_bruta", "ordem": "asc"},
    })

    assert "fora_da_lista_de_menor" not in resposta
    assert len(resposta["resultados"]) == 2
