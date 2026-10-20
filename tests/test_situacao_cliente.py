from datetime import date

import pandas as pd
import pytest

from core.motor import catalogo
from core.motor import orquestrador as orq
from core.repositories import situacao_cliente_repository as situacao

TIMON, CAXIAS = 9, 3
ZE, ANA, BIA, CARLOS, DANI, VELHO, EVA = 1, 2, 3, 4, 5, 6, 7


def _compras():
    linhas = [
        (ZE, TIMON, 10, "2026-06-27"),     # parado em Timon há 100 dias...
        (ZE, CAXIAS, 11, "2026-09-28"),    # ...mas comprou em Caxias
        (ANA, TIMON, 10, "2026-10-04"),    # 1ª compra: nova
        (BIA, TIMON, 10, "2026-06-07"),    # 120 dias: inativa
        (CARLOS, TIMON, 10, "2025-01-10"),
        (CARLOS, TIMON, 10, "2026-07-28"), # 69 dias: em risco
        (DANI, TIMON, 10, "2026-03-01"),
        (DANI, TIMON, 10, "2026-10-02"),   # 215 dias parada: recuperada
        (VELHO, TIMON, 10, "2025-01-05"),  # 638 dias: parado há mais de 1 ano
        (EVA, TIMON, 10, "2025-02-01"),    # comprou em Timon há tempo,
        (EVA, CAXIAS, 11, "2026-08-01"),   # mas a última foi em Caxias: só de Caxias
    ]
    compras = pd.DataFrame(linhas, columns=["CODCLI", "CODFILIAL", "COD_RCA", "DATA"])
    compras["COD_SUPERVISOR"] = 1
    compras["DATA"] = pd.to_datetime(compras["DATA"])
    return compras


def _foto(ano, mes, filial=TIMON):
    dados = situacao.montar_situacao(_compras(), [(ano, mes)], hoje=date(2026, 10, 5))
    foto = dados[(dados["ANO"] == ano) & (dados["MES"] == mes) & (dados["CODFILIAL"] == filial)]
    return foto.set_index("CODCLI")


def test_situacao_de_hoje():
    foto = _foto(2026, 10)

    assert set(foto.index) == {ZE, ANA, BIA, CARLOS, DANI, VELHO}   # a EVA não é de Timon
    assert set(foto.index[foto["ATIVO"] == 1]) == {ZE, ANA, CARLOS, DANI}
    assert set(foto.index[foto["EM_RISCO"] == 1]) == {CARLOS}
    assert set(foto.index[foto["INATIVO"] == 1]) == {BIA}
    assert set(foto.index[foto["PARADO_HA_MAIS_DE_1_ANO"] == 1]) == {VELHO}
    assert set(foto.index[foto["NOVO"] == 1]) == {ANA}
    assert set(foto.index[foto["RECUPERADO"] == 1]) == {DANI}
    assert foto.loc[CARLOS, "DIAS_SEM_COMPRAR"] == 69


def test_ativo_por_compra_em_outra_filial_fica_marcado():
    ze = _foto(2026, 10).loc[ZE]

    assert ze["ATIVO"] == 1 and ze["SO_OUTRA_FILIAL"] == 1
    assert ze["FILIAL_ULTIMA_COMPRA"] == CAXIAS
    assert ze["DATA_ULTIMA_COMPRA"] == pd.Timestamp("2026-09-28")


def test_mes_passado_usa_o_ultimo_dia_do_mes():
    # 30/09: a Bia (07/06) estava com 115 dias; o Carlos (28/07), com 64.
    foto = _foto(2026, 9)

    assert foto.loc[BIA, "INATIVO"] == 1
    assert foto.loc[CARLOS, "EM_RISCO"] == 1
    assert ANA not in foto.index


def test_cliente_da_filial_conta_os_12_meses_antes_da_ultima_compra():
    # A EVA comprou em Timon em 02/2025 e a última foi em Caxias, 08/2026:
    # é cliente de Caxias. O VELHO (parado desde 01/2025) segue de Timon.
    assert EVA not in _foto(2026, 10).index
    assert EVA in _foto(2026, 10, filial=CAXIAS).index
    assert _foto(2026, 10).loc[VELHO, "DIAS_SEM_COMPRAR"] == 638


def test_volta_depois_de_90_dias_e_recuperado():
    # O Carlos ficou de 10/01/2025 a 28/07/2026 sem comprar.
    assert _foto(2026, 7).loc[CARLOS, "RECUPERADO"] == 1


def test_guarda_quanto_tempo_ficou_parado_antes_de_voltar():
    # A Dani ficou de 01/03 a 02/10 (215 dias) parada; o Carlos, de
    # 10/01/2025 a 28/07/2026 (564). Quem não comprou no mês: 0.
    outubro, julho = _foto(2026, 10), _foto(2026, 7)

    assert outubro.loc[DANI, "DIAS_PARADO_ANTES_DE_VOLTAR"] == 215
    assert outubro.loc[CARLOS, "DIAS_PARADO_ANTES_DE_VOLTAR"] == 0
    assert julho.loc[CARLOS, "DIAS_PARADO_ANTES_DE_VOLTAR"] == 564


def test_parada_curta_conta_os_dias_mas_nao_e_recuperado():
    compras = pd.DataFrame({
        "CODCLI": [1, 1], "CODFILIAL": TIMON, "COD_RCA": 10, "COD_SUPERVISOR": 1,
        "DATA": pd.to_datetime(["2026-08-01", "2026-10-01"]),   # 61 dias
    })
    foto = situacao.montar_situacao(compras, [(2026, 10)], hoje=date(2026, 10, 5)).iloc[0]

    assert foto["DIAS_PARADO_ANTES_DE_VOLTAR"] == 61 and foto["RECUPERADO"] == 0


def test_atualizacao_parcial_troca_so_os_meses_recentes(monkeypatch, tmp_path):
    arquivo = tmp_path / "compras_clientes.csv"
    monkeypatch.setattr(situacao, "ARQUIVO_COMPRAS_CLIENTES", arquivo)
    monkeypatch.setattr(situacao, "inicio_da_janela_parcial", lambda: date(2026, 9, 1))
    monkeypatch.setattr(situacao, "_buscar", lambda desde: _compras())
    situacao.atualizar(completa=True)

    novas = _compras().iloc[[2]].assign(DATA=pd.Timestamp("2026-10-05"))
    monkeypatch.setattr(situacao, "_buscar", lambda desde: novas)
    situacao.atualizar(completa=False)

    datas = situacao._ler_compras()["DATA"]
    assert (datas >= pd.Timestamp("2026-09-01")).sum() == 1   # as 3 de set/out deram lugar à busca nova
    assert len(datas) == len(_compras()) - 3 + 1


# --- o indicador "clientes" no motor ---------------------------------------


def _situacao_para_o_motor():
    dados = situacao.montar_situacao(_compras(), [(2026, 9), (2026, 10)], hoje=date(2026, 10, 5))
    nomes = {TIMON: "TIMON", CAXIAS: "CAXIAS"}
    dados["FILIAL"] = dados["CODFILIAL"].map(nomes)
    dados["ESTADO"] = "MA"
    for marca in situacao._MARCAS:
        dados[f"CLIENTE_{marca}"] = dados["CODCLI"].where(dados[marca] == 1).astype("Int32")
    dados["SITUACAO"] = pd.Series(
        ["Inativo", "Ativo", "Em risco de perda", "Parado há mais de 1 ano"]
    ).iloc[dados["ATIVO"] + dados["EM_RISCO"] + 3 * dados["PARADO_HA_MAIS_DE_1_ANO"]].to_numpy()
    # Empresa: o Zé e o Velho são lojas da mesma.
    dados["EMPRESA"] = dados["CODCLI"].map({ZE: "E1", VELHO: "E1"}).fillna(dados["CODCLI"].astype(str))
    dados["ULTIMA_COMPRA"] = dados["DATA_ULTIMA_COMPRA"].dt.strftime("%d/%m/%Y")
    return dados


@pytest.fixture
def motor(monkeypatch):
    monkeypatch.setitem(catalogo.INDICADORES["clientes"], "carregar", _situacao_para_o_motor)
    monkeypatch.setitem(catalogo.INDICADORES["clientes"], "rca_requer_meta_cadastrada", False)


def _consultar(**consulta):
    return orq.executar_consulta({"indicador": "clientes", "filtros": {"filial": ["TIMON"]}, **consulta})


def test_ativos_de_timon_contam_cada_cliente_uma_vez(motor):
    resposta = _consultar(periodo="personalizado", periodo_personalizado={"meses": [10], "anos": [2026]})
    linha = resposta["resultados"][0]

    assert linha["clientes_ativos"] == 4 and linha["clientes_em_risco"] == 1
    assert linha["clientes_inativos"] == 1 and linha["ativos_so_em_outra_filial"] == 1
    assert linha["clientes_parados_ha_mais_de_1_ano"] == 1
    assert linha["clientes_novos"] == 1 and linha["clientes_recuperados"] == 1
    assert isinstance(linha["clientes_ativos"], int)


def test_aviso_de_outra_filial_ou_outro_rca_so_na_consulta_por_ela(motor):
    """'Ativos só por outra filial' só numa consulta por filial; 'só por
    outro RCA' só numa por RCA; na empresa toda, nenhum dos dois."""
    outubro = {"periodo": "personalizado", "periodo_personalizado": {"meses": [10], "anos": [2026]}}

    da_filial = _consultar(**outubro)["resultados"][0]
    assert "ativos_so_em_outra_filial" in da_filial and "ativos_so_com_outro_rca" not in da_filial

    da_empresa = orq.executar_consulta({"indicador": "clientes", **outubro})["resultados"][0]
    assert "ativos_so_em_outra_filial" not in da_empresa and "ativos_so_com_outro_rca" not in da_empresa

    por_filial = orq.executar_consulta({"indicador": "clientes", "agrupar_por": ["filial"], **outubro})
    assert "ativos_so_com_outro_rca" not in por_filial["total_de_todas_as_linhas"]


def test_periodo_de_varios_meses_usa_a_foto_do_ultimo(monkeypatch, motor):
    monkeypatch.setattr(orq, "date", _Hoje)
    # set a out/2026: ativos = foto de outubro (4), não a soma dos meses;
    # novos e recuperados juntam o período (Ana em out, Dani em out).
    resposta = _consultar(periodo="personalizado", periodo_personalizado={"meses": [9, 10], "anos": [2026]})
    linha = resposta["resultados"][0]

    assert linha["clientes_ativos"] == 4
    assert linha["clientes_novos"] == 1
    assert "05/10/2026" in resposta["situacao_na_data"]


def test_agrupado_por_mes_cada_mes_tem_a_sua_foto(motor):
    resposta = _consultar(
        periodo="personalizado", periodo_personalizado={"meses": [9, 10], "anos": [2026]},
        agrupar_por=["mes"],
    )
    por_mes = {linha["mes"]: linha for linha in resposta["resultados"]}

    # 30/09: Zé, Carlos, Dani(parada desde 01/03 → inativa) e Bia → ativos Zé e Carlos
    assert por_mes[9]["clientes_ativos"] == 2
    assert por_mes[10]["clientes_ativos"] == 4


class _Hoje(date):
    @classmethod
    def today(cls):
        return date(2026, 10, 5)

def test_ordena_pelos_dias_sem_comprar(monkeypatch, motor):
    monkeypatch.setattr(orq, "date", _Hoje)
    resposta = _consultar(
        periodo="mes_atual", agrupar_por=["cliente"],
        ordenar_por={"campo": "dias_sem_comprar", "limite": 2},
    )

    # Velho (638 dias) e Bia (120); o Zé conta 7 dias (comprou em Caxias).
    assert [linha["cliente"] for linha in resposta["resultados"]] == [VELHO, BIA]
    assert resposta["resultados"][0]["dias_sem_comprar"] == 638


def test_sem_periodo_diz_que_usou_a_situacao_de_hoje(monkeypatch, motor):
    monkeypatch.setattr(orq, "date", _Hoje)
    resposta = _consultar()

    assert "situação de hoje, 05/10/2026" in resposta["periodo_assumido"]


def test_lista_mes_a_mes_traz_a_variacao_de_cada_numero(monkeypatch, motor):
    from ui.formatacao import preparar_tabela

    resposta = _consultar(
        periodo="personalizado", periodo_personalizado={"meses": [9, 10], "anos": [2026]},
        agrupar_por=["mes"],
    )
    outubro = {linha["mes"]: linha for linha in resposta["resultados"]}[10]

    # ativos 2 → 4 (+100%); inativos 2 (Bia, Dani) → 1 (Bia) (−50%)
    assert outubro["percentual_clientes_ativos_mes_anterior"] == 100.0
    assert outubro["percentual_clientes_inativos_mes_anterior"] == -50.0

    tabela = preparar_tabela(resposta["resultados"], "clientes ativos e inativos", "consultar_dados_comerciais")
    assert list(tabela.columns) == [
        "Mês", "Clientes Ativos", "Variação Clientes Ativos (mês anterior)",
        "Inativos até 1 ano", "Variação Inativos até 1 ano (mês anterior)",
        "Parados há mais de 1 ano", "Variação Parados há mais de 1 ano (mês anterior)",
    ]


def test_ordem_por_contagem_de_clientes_por_cliente_e_ignorada(motor):
    # A ordem pelos novos (0 ou 1 por cliente) junto do filtro sai e a lista
    # vem.
    resposta = _consultar(
        periodo="personalizado", periodo_personalizado={"meses": [10], "anos": [2026]},
        agrupar_por=["cliente"],
        filtros_calculados=[{"campo": "clientes_novos", "operador": ">=", "valor": 1}],
        ordenar_por={"campo": "clientes_novos", "ordem": "desc", "limite": 10},
    )

    assert [linha["cliente"] for linha in resposta["resultados"]] == [ANA]


def test_carrega_so_a_foto_dos_meses_pedidos(monkeypatch):
    monkeypatch.setattr(situacao, "_garantir", lambda: None)
    monkeypatch.setattr(situacao, "_ler_compras", _compras)
    monkeypatch.setattr(situacao.cliente_repository, "carregar_clientes", lambda: pd.DataFrame(
        {"CODCLI": range(1, 8), "CLIENTE": "X", "CNPJ": "1", "CIDADE": "TIMON",
         "EMPRESA": "1", "NOME_EMPRESA": "X", "CNPJ_EMPRESA": "1"}
    ))
    monkeypatch.setitem(situacao._cache, "versao", None)

    dados = situacao.carregar_situacao_clientes({"ano": [2026], "mes": [9]})

    assert set(zip(dados["ANO"], dados["MES"])) == {(2026, 9)}
    with pytest.raises(ValueError, match="começa em 2021"):
        situacao.carregar_situacao_clientes({"ano": [2020]})


def test_resposta_traz_o_como_ler_do_indicador(motor):
    resposta = _consultar()

    assert "parados há mais de 1 ano" in resposta["como_ler_o_indicador"]["clientes"]


# --- prazos ("sem comprar há…") e a lista de clientes ----------------------

_OUTUBRO = {"periodo": "personalizado", "periodo_personalizado": {"meses": [10], "anos": [2026]}}


def _lista(*filtros, **consulta):
    resposta = _consultar(
        **{**_OUTUBRO, **consulta}, agrupar_por=["cliente"],
        filtros_calculados=[
            {"campo": campo, "operador": operador, "valor": valor}
            for campo, operador, valor in filtros
        ],
    )
    return resposta, [linha["cliente"] for linha in resposta["resultados"]]


def test_ha_mais_de_2_meses_separa_por_situacao_e_vem_dos_mais_recentes(motor):
    # Carlos 69 dias (em risco), Bia 120 (inativa), Velho 638 (parado).
    resposta, clientes = _lista(("dias_sem_comprar", ">=", 60))

    assert clientes == [CARLOS, BIA, VELHO]
    assert resposta["quantos_por_situacao"]["quantidade"] == {
        "Em risco de perda": 1, "Inativo": 1, "Parado há mais de 1 ano": 1,
    }
    assert "do menor para o maior" in resposta["criterio_da_ordem"]


def test_ha_2_meses_e_de_60_a_89_dias(motor):
    _, clientes = _lista(("dias_sem_comprar", ">=", 60), ("dias_sem_comprar", "<=", 89))

    assert clientes == [CARLOS]


def test_ha_7_dias_e_exatamente_7(motor):
    _, clientes = _lista(("dias_sem_comprar", "==", 7))

    assert clientes == [ZE]


def test_ordem_pedida_vale_mais_que_a_da_lista(motor):
    resposta, clientes = _lista(
        ("dias_sem_comprar", ">=", 60),
        ordenar_por={"campo": "dias_sem_comprar", "ordem": "desc"},
    )

    assert clientes == [VELHO, BIA, CARLOS]
    assert "Sem ordem pedida" not in resposta["criterio_da_ordem"]


def test_ficou_5_meses_parado_e_voltou(motor):
    # Set/out de 2026: só a Dani voltou depois de 150+ dias (215).
    resposta, clientes = _lista(
        ("dias_parado_antes_de_voltar", ">=", 150),
        periodo="personalizado", periodo_personalizado={"meses": [9, 10], "anos": [2026]},
    )

    assert clientes == [DANI]
    assert resposta["resultados"][0]["dias_parado_antes_de_voltar"] == 215


def test_empresa_esta_sem_comprar_desde_a_compra_mais_recente_das_lojas(motor):
    # Zé (7 dias) e Velho (638) são lojas da mesma empresa.
    resposta = _consultar(**_OUTUBRO, agrupar_por=["empresa"])
    empresa = {linha["empresa"]: linha for linha in resposta["resultados"]}["E1"]

    assert empresa["dias_sem_comprar"] == 7
    # A data também é a da loja que comprou por último (o Zé, há 7 dias).
    assert empresa["ultima_compra"] == "28/09/2026"
    assert "quantos_por_situacao" not in resposta


def test_lista_de_clientes_sem_coluna_de_contagem_e_com_o_dia_da_situacao(motor):
    """Numa lista por cliente, "em risco" é 1 em toda linha: sai da tabela
    (a situação já diz). A legenda é o dia da situação, não o ano."""
    resposta = _consultar(
        **_OUTUBRO, agrupar_por=["cliente"],
        filtros_calculados=[{"campo": "clientes_em_risco", "operador": ">", "valor": 0}],
        colunas=["clientes_em_risco", "dias_sem_comprar"],
    )
    linha = resposta["tabela"][0]

    assert linha["_colunas_pedidas"] == ["dias_sem_comprar"]
    assert linha["_legenda"].startswith("Situação ")


def test_lista_de_clientes_sem_colunas_pedidas_mostra_os_dias_sem_comprar(motor):
    """'Quais clientes estão em risco' sem "colunas": tirada a contagem (1
    por cliente), a tabela mostra o campo da ordem da lista — sem nenhuma
    coluna de valor, a tela não mostrava tabela nenhuma."""
    resposta = _consultar(
        **_OUTUBRO, agrupar_por=["cliente"],
        filtros_calculados=[{"campo": "clientes_em_risco", "operador": ">", "valor": 0}],
    )

    assert resposta["tabela"][0]["_colunas_pedidas"] == ["dias_sem_comprar"]
