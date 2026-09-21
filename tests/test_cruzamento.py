"""Testes do cruzamento de indicadores ("cruzar_com") do motor genérico."""
import pandas as pd
import pytest

from src import catalogo
from src import orquestrador as orq
from src.exceptions import ConsultaInvalida


def _nps():
    def linha(filial, dia, nota):
        data = pd.Timestamp(dia)
        return {
            "FILIAL": filial, "DATA": data, "MES": data.month, "ANO": data.year,
            "RESPOSTA": 1, "PROMOTOR": int(nota >= 9),
            "NEUTRO": int(7 <= nota <= 8), "DETRATOR": int(nota <= 6),
        }

    return pd.DataFrame(
        [
            # TIMON jul/2025: 3 promotores + 1 detrator -> NPS 50
            linha("TIMON", "2025-07-01", 10), linha("TIMON", "2025-07-02", 9),
            linha("TIMON", "2025-07-03", 10), linha("TIMON", "2025-07-04", 3),
            # TIMON ago/2025: 1 promotor -> NPS 100
            linha("TIMON", "2025-08-01", 10),
            # TIBIRI jul/2025: 1 promotor + 1 detrator -> NPS 0
            linha("TIBIRI", "2025-07-01", 10), linha("TIBIRI", "2025-07-02", 2),
            # MARITUBA não tem meta cadastrada, só NPS
            linha("MARITUBA", "2025-07-01", 10),
        ]
    )


def _meta():
    def linha(filial, mes, realizado, meta):
        return {
            "FILIAL": filial, "COD_RCA": 1, "COD_SUPERVISOR": 1, "MES": mes,
            "ANO": 2025, "VENDA_LIQ": realizado, "VALOR_META": meta,
        }

    return pd.DataFrame(
        [
            linha("TIMON", 7, 120.0, 100.0),    # bateu (120%)
            linha("TIMON", 8, 50.0, 100.0),     # não bateu (50%)
            linha("TIBIRI", 7, 80.0, 100.0),    # não bateu (80%)
            # sem NPS em setembro
            linha("TIMON", 9, 100.0, 100.0),
        ]
    )


@pytest.fixture(autouse=True)
def _bases(monkeypatch):
    monkeypatch.setitem(catalogo.INDICADORES["nps"], "carregar", _nps)
    monkeypatch.setitem(catalogo.INDICADORES["meta"], "carregar", _meta)


def _consultar(**extra):
    consulta = {
        "indicador": "nps",
        "cruzar_com": ["meta"],
        "filtros": {"ano": [2025]},
        **extra,
    }
    return orq.executar_consulta(consulta)


def test_cruza_por_filial_com_os_campos_dos_dois_indicadores():
    resultado = _consultar(
        filtros={"ano": [2025], "mes": [7]}, agrupar_por=["filial"]
    )

    por_filial = {item["filial"]: item for item in resultado["resultados"]}

    assert resultado["cruzado_com"] == ["meta"]
    assert por_filial["TIMON"]["nps"] == 50.0
    assert por_filial["TIMON"]["percentual_atingimento"] == 120.0
    assert por_filial["TIBIRI"]["nps"] == 0.0
    assert por_filial["TIBIRI"]["percentual_atingimento"] == 80.0


def test_filial_que_so_existe_num_indicador_fica_com_o_outro_vazio():
    resultado = _consultar(
        filtros={"ano": [2025], "mes": [7]}, agrupar_por=["filial"]
    )

    maritub = next(i for i in resultado["resultados"] if i["filial"] == "MARITUBA")

    assert maritub["nps"] == 100.0
    assert maritub["percentual_atingimento"] is None
    assert maritub["valor_meta"] is None


def test_maior_nps_entre_quem_bateu_a_meta():
    """O filtro sobre a meta e a ordenação pelo NPS valem na tabela junta."""
    resultado = _consultar(
        filtros={"ano": [2025], "mes": [7]},
        agrupar_por=["filial"],
        filtros_calculados=[
            {"campo": "percentual_atingimento", "operador": ">=", "valor": 100}
        ],
        ordenar_por={"campo": "nps", "ordem": "desc", "limite": 1},
    )

    assert [item["filial"] for item in resultado["resultados"]] == ["TIMON"]


def test_cruza_mes_a_mes_e_mantem_o_mes_que_so_tem_um_indicador_em_ordem():
    resultado = _consultar(
        filtros={"ano": [2025], "filial": ["Timon"]}, agrupar_por=["mes"]
    )

    meses = [(i["mes"], i["nps"], i["percentual_atingimento"]) for i in resultado["resultados"]]

    # setembro só tem meta (sem NPS) e não pode ir parar no fim da lista
    assert meses == [(7, 50.0, 120.0), (8, 100.0, 50.0), (9, None, 100.0)]


def test_sem_agrupar_devolve_uma_linha_com_os_dois_indicadores():
    resultado = _consultar(filtros={"ano": [2025], "mes": [7], "filial": ["Timon"]})

    assert len(resultado["resultados"]) == 1
    assert resultado["resultados"][0]["nps"] == 50.0
    assert resultado["resultados"][0]["percentual_atingimento"] == 120.0


def test_comparar_com_funciona_junto_com_o_cruzamento(monkeypatch):
    def nps_com_2024():
        dados = _nps()
        extra = dados[dados["FILIAL"] == "TIMON"].iloc[[0]].copy()
        extra["DATA"] = pd.Timestamp("2024-07-01")
        extra["ANO"] = 2024
        extra["PROMOTOR"], extra["DETRATOR"] = 0, 1  # NPS -100 em 2024
        return pd.concat([dados, extra], ignore_index=True)

    def meta_com_2024():
        dados = _meta()
        extra = dados.iloc[[0]].copy()
        extra["ANO"], extra["VENDA_LIQ"] = 2024, 60.0  # 60% em 2024
        return pd.concat([dados, extra], ignore_index=True)

    monkeypatch.setitem(catalogo.INDICADORES["nps"], "carregar", nps_com_2024)
    monkeypatch.setitem(catalogo.INDICADORES["meta"], "carregar", meta_com_2024)

    resultado = _consultar(
        filtros={"ano": [2025], "mes": [7], "filial": ["Timon"]},
        comparar_com="ano_anterior_ao_filtro",
    )

    linha = resultado["resultados"][0]

    assert linha["nps_anterior"] == -100.0
    assert linha["diferenca_nps"] == 150.0
    assert linha["percentual_atingimento_anterior"] == 60.0


@pytest.mark.parametrize(
    "consulta",
    [
        {"indicador": "faturamento", "cruzar_com": ["meta_tonelada"], "agrupar_por": ["rca"]},
        {"indicador": "faturamento", "cruzar_com": ["faturamento_diario"]},
        {"indicador": "nps", "cruzar_com": ["nps"]},
        {"indicador": "nps", "cruzar_com": ["indicador_que_nao_existe"]},
        {"indicador": "nps", "cruzar_com": ["meta"], "filtros": {"rca": ["1"]}},
        {"indicador": "nps", "cruzar_com": ["meta"], "ordenar_por": {"campo": "campo_que_nao_existe"}},
    ],
)
def test_cruzamento_invalido_gera_erro_claro(consulta):
    with pytest.raises(ConsultaInvalida):
        orq.executar_consulta(consulta)


def test_ordenar_por_aceita_campo_de_qualquer_indicador_cruzado():
    resultado = _consultar(
        filtros={"ano": [2025], "mes": [7]},
        agrupar_por=["filial"],
        ordenar_por={"campo": "percentual_atingimento", "ordem": "desc", "limite": 1},
    )

    assert [item["filial"] for item in resultado["resultados"]] == ["TIMON"]


def _faturamento_com_peso():
    def linha(filial, peso_kg):
        return {
            "FILIAL": filial, "MES": 7, "ANO": 2025, "VENDA_LIQ": 1.0,
            "VENDA_BRUTA": 1.0, "VALORDESC": 0.0, "PESOLIQ": peso_kg,
            "QT_NOTAS": 1,
        }

    return pd.DataFrame(
        [linha("TIMON", 1_000_000), linha("TIBIRI", 500_000), linha("PICOS", 300_000)]
    )


def _meta_tonelada():
    def linha(filial, meta):
        return {
            "FILIAL": filial, "ANO": 2025, "MES": 7, "RCA": "X",
            "Meta Tonelada - Filial": meta, "Meta Tonelada - RCA": meta,
        }

    # PICOS não tem meta cadastrada; ARACAGY tem meta mas não vendeu nada
    return pd.DataFrame(
        [linha("TIMON", 800.0), linha("TIBIRI", 1000.0), linha("ARACAGY", 200.0)]
    )


def _consultar_tonelada(**extra):
    return orq.executar_consulta(
        {
            "indicador": "faturamento",
            "cruzar_com": ["meta_tonelada"],
            "filtros": {"ano": [2025]},
            "agrupar_por": ["filial"],
            **extra,
        }
    )


@pytest.fixture
def _bases_tonelada(monkeypatch):
    monkeypatch.setitem(catalogo.INDICADORES["faturamento"], "carregar", _faturamento_com_peso)
    monkeypatch.setitem(catalogo.INDICADORES["meta_tonelada"], "carregar", _meta_tonelada)


def test_atingimento_da_meta_de_tonelada_cruza_toneladas_com_a_meta(_bases_tonelada):
    resultado = _consultar_tonelada()

    por_filial = {i["filial"]: i for i in resultado["resultados"]}

    assert por_filial["TIMON"]["toneladas"] == 1000.0
    assert por_filial["TIMON"]["percentual_atingimento_tonelada"] == 125.0
    assert por_filial["TIMON"]["falta_para_meta_tonelada"] == 0.0
    assert por_filial["TIBIRI"]["percentual_atingimento_tonelada"] == 50.0
    assert por_filial["TIBIRI"]["falta_para_meta_tonelada"] == 500.0


def test_filial_sem_meta_ou_sem_venda_fica_sem_atingimento_e_nao_quebra(_bases_tonelada):
    resultado = _consultar_tonelada()

    por_filial = {i["filial"]: i for i in resultado["resultados"]}

    assert por_filial["PICOS"]["percentual_atingimento_tonelada"] is None  # sem meta
    assert por_filial["ARACAGY"]["percentual_atingimento_tonelada"] is None  # sem venda


def test_quais_filiais_bateram_a_meta_de_tonelada(_bases_tonelada):
    resultado = _consultar_tonelada(
        filtros_calculados=[
            {"campo": "percentual_atingimento_tonelada", "operador": ">=", "valor": 100}
        ]
    )

    assert [i["filial"] for i in resultado["resultados"]] == ["TIMON"]


def test_campo_de_atingimento_de_tonelada_so_existe_ao_cruzar(_bases_tonelada):
    with pytest.raises(ConsultaInvalida):
        orq.executar_consulta(
            {
                "indicador": "faturamento",
                "agrupar_por": ["filial"],
                "ordenar_por": {"campo": "percentual_atingimento_tonelada"},
            }
        )
