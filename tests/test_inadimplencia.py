from datetime import date

import pandas as pd

from core.motor import catalogo
from core.motor import orquestrador as orq
from core.repositories import inadimplencia_repository as inadimplencia

HOJE = date(2026, 10, 28)
TIMON = 9
ZE, ANA, BIA = 1, 2, 3


def _titulos():
    linhas = [
        # (cliente, vencimento, pagamento, valor)
        (ZE, "2026-08-05", None, 1000.0),          # agosto, aberto: oficial e em atraso
        (ZE, "2026-08-20", "2026-10-15", 500.0),   # pago depois de 10/10: só oficial
        (ANA, "2026-09-10", None, 300.0),          # setembro não fechou: só em atraso
        (BIA, "2026-10-05", None, 200.0),          # 23 dias: risco de bloqueio
        (BIA, "2026-10-20", None, 100.0),
    ]
    titulos = pd.DataFrame(linhas, columns=["CODCLI", "DTVENC", "DTPAG", "VALOR"])
    titulos["DTVENC"] = pd.to_datetime(titulos["DTVENC"])
    titulos["DTPAG"] = pd.to_datetime(titulos["DTPAG"])
    titulos["CODFILIAL"] = TIMON
    return titulos


def test_data_do_fechamento_e_dia_10_de_dois_meses_depois():
    datas = inadimplencia.data_do_fechamento(pd.Series([2026, 2026]), pd.Series([8, 11]))

    assert list(datas) == [pd.Timestamp("2026-10-10"), pd.Timestamp("2027-01-10")]


def test_oficial_em_atraso_e_risco_de_bloqueio():
    dados = inadimplencia.marcar_situacao(_titulos(), HOJE).set_index(["CODCLI", "VALOR"])

    assert dados["VALOR_INADIMPLENTE"].sum() == 1500.0          # só agosto (fechado em 10/10)
    assert dados["VALOR_EM_ATRASO"].sum() == 1600.0             # tudo que está aberto hoje
    assert dados.loc[(ZE, 500.0), "TITULO_EM_ATRASO"] == 0      # já foi pago
    assert dados.loc[(BIA, 200.0), "DIAS_DE_ATRASO"] == 23
    assert set(dados["CLIENTE_EM_RISCO_DE_BLOQUEIO"].dropna()) == {BIA}
    # O título de 8 dias da Bia também marca: vale o mais atrasado dela.
    assert dados.loc[(BIA, 100.0), "DIAS_PARA_O_BLOQUEIO"] == 7
    assert dados["CLIENTE_EM_RISCO_DE_BLOQUEIO"].loc[ZE].isna().all()   # 84 dias: já passou


def test_faturamento_so_dos_meses_fechados_inclusive_sem_titulo():
    dados = inadimplencia.marcar_situacao(_titulos(), HOJE)
    faturamento = pd.DataFrame({
        "CODFILIAL": TIMON, "ANO": 2026, "MES": [7, 8, 9], "VENDA_LIQ": [70000.0, 80000.0, 90000.0],
    })

    dados = inadimplencia.com_faturamento(dados, faturamento, HOJE)
    por_mes = dados.groupby("MES")["FATURAMENTO_LIQ"].max()

    assert por_mes[7] == 70000.0      # julho: sem título, linha só pro faturamento
    assert por_mes[8] == 80000.0
    assert pd.isna(por_mes[9])        # setembro ainda não fechou
    assert dados["VALOR_INADIMPLENTE"].sum() == 1500.0


def test_percentual_por_filial_e_lista_de_clientes_sem_linha_vazia(monkeypatch):
    dados = inadimplencia.marcar_situacao(_titulos(), HOJE)
    faturamento = pd.DataFrame({
        "CODFILIAL": TIMON, "ANO": 2026, "MES": [7, 8], "VENDA_LIQ": [70000.0, 80000.0],
    })
    dados = inadimplencia.com_faturamento(dados, faturamento, HOJE)
    dados = dados.assign(FILIAL="TIMON", ESTADO="MA")
    monkeypatch.setitem(catalogo.INDICADORES["inadimplencia"], "carregar", lambda: dados)

    resposta = orq.executar_consulta({"indicador": "inadimplencia"})
    # Sem período, o oficial é o do último mês fechado, não "todo o histórico".
    assert "último mês fechado" in resposta["periodo_consultado"]["descricao"]
    total = resposta["resultados"][0]
    # 1.500 oficiais ÷ 150.000 de faturamento (julho + agosto).
    assert total["percentual_inadimplencia"] == 1.0
    assert total["clientes_em_risco_de_bloqueio"] == 1

    clientes = orq.executar_consulta({"indicador": "inadimplencia", "agrupar_por": ["cliente"]})["resultados"]
    assert sorted(linha["cliente"] for linha in clientes) == [ZE, ANA, BIA]


def test_percentual_por_rca_divide_pelo_faturamento_da_filial_no_periodo_todo(monkeypatch):
    dados = inadimplencia.marcar_situacao(_titulos(), HOJE)
    dados["COD_RCA"] = dados["CODCLI"].map({ZE: 10, ANA: 20, BIA: 20})
    faturamento = pd.DataFrame({
        "CODFILIAL": TIMON, "ANO": 2026, "MES": [7, 8], "VENDA_LIQ": [70000.0, 80000.0],
    })
    dados = inadimplencia.com_faturamento(dados, faturamento, HOJE).assign(FILIAL="TIMON", ESTADO="MA")
    monkeypatch.setitem(catalogo.INDICADORES["inadimplencia"], "carregar", lambda: dados)
    monkeypatch.delitem(catalogo.INDICADORES["inadimplencia"], "rca_nome_mapa")

    resposta = orq.executar_consulta({"indicador": "inadimplencia", "agrupar_por": ["rca"]})
    por_rca = {linha["rca"]: linha for linha in resposta["resultados"]}

    # O RCA 10 só tem título em agosto, mas divide por julho + agosto.
    assert por_rca[10]["faturamento_liquido"] == 150000.0
    assert por_rca[10]["percentual_inadimplencia"] == 1.0
    # Sem título em mês fechado: 0%, não vazio.
    assert por_rca[20]["percentual_inadimplencia"] == 0.0



def test_mes_nao_fechado_fica_vazio_sem_variacao_de_100(monkeypatch):
    dados = inadimplencia.marcar_situacao(_titulos(), HOJE)
    faturamento = pd.DataFrame({"CODFILIAL": TIMON, "ANO": 2026, "MES": [8], "VENDA_LIQ": [80000.0]})
    dados = inadimplencia.com_faturamento(dados, faturamento, HOJE).assign(FILIAL="TIMON", ESTADO="MA")
    monkeypatch.setitem(catalogo.INDICADORES["inadimplencia"], "carregar", lambda: dados)
    monkeypatch.setitem(catalogo.INDICADORES["inadimplencia"]["periodo_dos_campos"], "ultimo_mes_fechado", lambda: (2026, 8))

    resposta = orq.executar_consulta({"indicador": "inadimplencia", "filtros": {"ano": [2026]}, "agrupar_por": ["mes"]})
    por_mes = {linha["mes"]: linha for linha in resposta["resultados"]}

    assert por_mes[8]["valor_inadimplente"] == 1500.0
    assert por_mes[9]["valor_inadimplente"] is None           # ainda não fechou: vazio, não zero
    assert por_mes[9]["faturamento_liquido"] is None
    assert por_mes[9]["percentual_valor_inadimplente_mes_anterior"] is None   # e não -100%
    assert por_mes[9]["valor_em_atraso"] == 300.0             # o em atraso continua

def test_sem_periodo_o_oficial_e_o_do_ultimo_mes_fechado():
    titulos = pd.concat([
        _titulos(),
        pd.DataFrame({
            # Maio: um aberto e um pago depois do fechamento (10/07).
            "CODCLI": [ANA, 9], "DTVENC": pd.to_datetime(["2026-05-10", "2026-05-12"]),
            "DTPAG": pd.to_datetime([None, "2026-09-01"]),
            "VALOR": [700.0, 400.0], "CODFILIAL": [TIMON, TIMON],
        }),
    ], ignore_index=True)
    dados = inadimplencia.marcar_situacao(titulos, HOJE)
    faturamento = pd.DataFrame({"CODFILIAL": TIMON, "ANO": 2026, "MES": [5, 8], "VENDA_LIQ": [50000.0, 80000.0]})
    dados = inadimplencia.com_faturamento(dados, faturamento, HOJE)

    dados = inadimplencia.so_o_ultimo_mes_fechado(dados, HOJE)

    assert dados["VALOR_INADIMPLENTE"].sum() == 1500.0      # só agosto (maio fica de fora)
    assert dados["FATURAMENTO_LIQ"].dropna().unique().tolist() == [80000.0]
    assert dados["VALOR_EM_ATRASO"].sum() == 2300.0         # o em atraso junta tudo
    assert set(dados["CLIENTE_INADIMPLENTE"].dropna()) == {ZE}
    assert 9 not in set(dados["CODCLI"])                   # já pagou: não vira cliente zerado


def test_descrever_fechamento():
    texto = inadimplencia.descrever_fechamento(hoje=HOJE)

    assert "10/10/2026" in texto and "agosto de 2026" in texto
    assert "Setembro de 2026 fecha em 10/11/2026" in texto
    assert "último mês fechado, agosto de 2026" in texto
    assert "último mês fechado" not in inadimplencia.descrever_fechamento({"ano": [2026]}, hoje=HOJE)

