"""Comparação entre dois itens da mesma dimensão ("comparar_filtros")."""
import pandas as pd
import pytest

from app import preparar_tabela
from src import catalogo
from src import orquestrador as orq
from src.exceptions import ConsultaInvalida


def _nps():
    def linha(filial, mes, nota):
        data = pd.Timestamp(2025, mes, 10)
        return {
            "FILIAL": filial, "DATA": data, "MES": mes, "ANO": 2025,
            "RESPOSTA": 1, "PROMOTOR": int(nota >= 9),
            "NEUTRO": int(7 <= nota <= 8), "DETRATOR": int(nota <= 6),
        }

    return pd.DataFrame(
        [
            # TIMON: jan NPS 100, fev NPS 0
            linha("TIMON", 1, 10), linha("TIMON", 2, 10), linha("TIMON", 2, 2),
            # LOURIVAL: jan NPS 0 (1 promotor + 1 detrator), mar NPS 100
            linha("LOURIVAL", 1, 10), linha("LOURIVAL", 1, 3), linha("LOURIVAL", 3, 10),
        ]
    )


@pytest.fixture(autouse=True)
def _base(monkeypatch):
    monkeypatch.setitem(catalogo.INDICADORES["nps"], "carregar", _nps)


def _comparar(**extra):
    consulta = {
        "indicador": "nps",
        "filtros": {"filial": ["TIMON"], "ano": [2025]},
        "comparar_filtros": {"filial": ["LOURIVAL"]},
        "agrupar_por": ["mes"],
        "colunas": ["nps"],
        **extra,
    }
    return orq.executar_consulta(consulta)


def test_compara_os_dois_itens_mes_a_mes_com_a_diferenca_a_menos_b():
    resultado = _comparar()

    por_mes = {i["mes"]: i for i in resultado["resultados"]}

    assert por_mes[1]["nps"] == 100.0 and por_mes[1]["nps_anterior"] == 0.0
    assert por_mes[1]["diferenca_nps"] == 100.0
    assert resultado["comparacao_entre"]["a"] == "TIMON"
    assert resultado["comparacao_entre"]["b"] == "LOURIVAL"


def test_mes_em_que_so_um_lado_tem_dado_nao_some_e_sai_em_ordem():
    resultado = _comparar()

    meses = [(i["mes"], i["nps"], i["nps_anterior"]) for i in resultado["resultados"]]

    # fev: só TIMON; mar: só LOURIVAL
    assert meses == [(1, 100.0, 0.0), (2, 0.0, None), (3, None, 100.0)]
    assert resultado["resultados"][1]["diferenca_nps"] is None


def test_nao_calcula_a_variacao_mes_a_mes_de_cada_filial():
    """Comparar dois itens entre si não é a evolução de cada um no tempo."""
    resultado = _comparar()

    assert "percentual_mes_anterior" not in resultado["resultados"][0]


def test_sem_agrupar_compara_o_total_do_periodo():
    resultado = _comparar(agrupar_por=[])

    linha = resultado["resultados"][0]

    # TIMON: 2 promotores e 1 detrator em 3 respostas; LOURIVAL: idem
    assert len(resultado["resultados"]) == 1
    assert linha["nps"] == 33.33 and linha["nps_anterior"] == 33.33
    assert linha["diferenca_nps"] == 0.0


def test_tabela_traz_os_nomes_dos_dois_lados_nos_titulos_das_colunas():
    resultado = _comparar()

    tabela = preparar_tabela(resultado["tabela"], "comparação", "consultar_dados_comerciais")

    assert list(tabela.columns) == [
        "Mês", "TIMON", "LOURIVAL",
        "Diferença (TIMON − LOURIVAL)", "Diferença % (TIMON vs LOURIVAL)",
    ]
    assert tabela.iloc[0]["Diferença (TIMON − LOURIVAL)"] == "+100,00"
    assert tabela.iloc[1]["LOURIVAL"] == "sem dados"


def test_comparar_periodo_e_item_juntos_viram_cada_item_periodo_contra_periodo(monkeypatch):
    """"Timon e Lourival, 2025 contra 2024": a IA às vezes manda os dois tipos
    de comparação ao mesmo tempo — o motor lê como cada filial, ano contra ano."""
    def nps_com_2024():
        dados = _nps()
        extra = dados[dados["FILIAL"] == "TIMON"].iloc[[0]].copy()
        extra["DATA"], extra["ANO"] = pd.Timestamp(2024, 1, 10), 2024
        extra["PROMOTOR"], extra["DETRATOR"] = 0, 1  # NPS -100 em 2024
        return pd.concat([dados, extra], ignore_index=True)

    monkeypatch.setitem(catalogo.INDICADORES["nps"], "carregar", nps_com_2024)

    resultado = orq.executar_consulta(
        {
            "indicador": "nps",
            "filtros": {"filial": ["TIMON"], "ano": [2025]},
            "comparar_filtros": {"filial": ["LOURIVAL"]},
            "comparar_com": "ano_anterior_ao_filtro",
        }
    )

    por_filial = {i["filial"]: i for i in resultado["resultados"]}

    assert set(por_filial) == {"TIMON", "LOURIVAL"}
    assert por_filial["TIMON"]["nps_anterior"] == -100.0
    assert "comparacao_entre" not in resultado


def test_sem_colunas_a_tabela_usa_o_campo_principal():
    resultado = _comparar(colunas=None)

    assert "tabela" in resultado
    assert "nps" in resultado["tabela"][0]


@pytest.mark.parametrize(
    "extra",
    [
        {"agrupar_por": ["filial"]},  # a dimensão comparada não pode agrupar
        {"comparar_filtros": {"rca": ["1"]}},  # filtro que o indicador não tem
    ],
)
def test_comparacao_invalida_gera_erro_claro(extra):
    with pytest.raises(ConsultaInvalida):
        _comparar(**extra)
