import pandas as pd
import pytest

from core.motor import catalogo
from core.motor import orquestrador as orq
from core.repositories import venda_repository


def _vendas():
    return pd.DataFrame([
        {"FILIAL": "TIMON", "ESTADO": "MA", "CODFILIAL": 9, "ANO": 2026, "MES": 9,
         "DATA": pd.Timestamp("2026-09-10"), "DATA_TEXTO": "10/09/2026", "NUMTRANSVENDA": 1,
         "NUMNOTA": 500, "NUMPED": 9001, "CODCLI": 7, "CLIENTE": "CLIENTE A", "EMPRESA": "11111111",
         "NOME_EMPRESA": "A", "COD_RCA": 10, "NOME_RCA": "ANA", "COD_SUPERVISOR": 9,
         "VALORDESC": 50.0, "VENDA_TABELA": 1000.0, "VENDA_BRUTA": 950.0},
        {"FILIAL": "CAXIAS", "ESTADO": "MA", "CODFILIAL": 3, "ANO": 2026, "MES": 9,
         "DATA": pd.Timestamp("2026-09-11"), "DATA_TEXTO": "11/09/2026", "NUMTRANSVENDA": 2,
         "NUMNOTA": 500, "NUMPED": 9002, "CODCLI": 8, "CLIENTE": "CLIENTE B", "EMPRESA": "22222222",
         "NOME_EMPRESA": "B", "COD_RCA": 11, "NOME_RCA": "BIA", "COD_SUPERVISOR": 9,
         "VALORDESC": 5.0, "VENDA_TABELA": 500.0, "VENDA_BRUTA": 495.0},
    ])


@pytest.fixture
def vendas(monkeypatch):
    monkeypatch.setattr(venda_repository, "carregar_desconto_venda", _vendas)


def test_nota_repetida_a_filial_escolhe(vendas):
    assert venda_repository.resolver_vendas("500", filiais=["TIMON"]) == [1]
    assert venda_repository.resolver_vendas("9002") == [2]   # pelo pedido


def test_numero_inexistente_ou_texto_avisa(vendas):
    with pytest.raises(ValueError, match="Não encontrei"):
        venda_repository.resolver_vendas("123")
    with pytest.raises(ValueError, match="não é um número"):
        venda_repository.resolver_vendas("a maior")


def test_ranking_de_vendas_traz_nota_cliente_e_rca(monkeypatch, vendas):
    monkeypatch.setitem(catalogo.INDICADORES["desconto"]["fontes_por_dimensao"], "venda", _vendas)

    resposta = orq.executar_consulta({
        "indicador": "desconto", "filtros": {"ano": [2026]}, "agrupar_por": ["venda"],
        "ordenar_por": {"campo": "valor_desconto", "limite": 1},
    })

    venda = resposta["resultados"][0]
    assert venda["valor_desconto"] == 50.0 and venda["percentual_desconto"] == 5.0
    assert (venda["venda_nota"], venda["venda_cliente"], venda["venda_rca"]) == ("500", "CLIENTE A", "ANA")


def test_mesma_nota_em_filiais_diferentes_pergunta_qual(vendas):
    with pytest.raises(ValueError, match="filiais diferentes"):
        venda_repository.resolver_vendas("500")


def test_atualizacao_parcial_mantem_um_formato_de_data(monkeypatch, tmp_path):
    arquivo = tmp_path / "desconto_venda.csv"
    monkeypatch.setattr(venda_repository, "ARQUIVO_DESCONTO_VENDA", arquivo)
    linha = {"CODFILIAL": 9, "ANO": 2025, "MES": 1, "NUMTRANSVENDA": 1, "NUMNOTA": 1, "NUMPED": 1,
             "CODCLI": 1, "COD_RCA": 1, "COD_SUPERVISOR": 1, "QT_ITENS": 1,
             "VALORDESC": 1.0, "VENDA_TABELA": 10.0, "VENDA_BRUTA": 9.0}
    venda_repository.gravar_csv(
        pd.DataFrame([{**linha, "DATA": pd.Timestamp("2025-01-02")}])[venda_repository.COLUNAS], arquivo
    )
    monkeypatch.setattr(venda_repository, "_buscar", lambda desde: pd.DataFrame(
        [{**linha, "NUMTRANSVENDA": 2, "ANO": 2026, "MES": 10, "DATA": pd.Timestamp("2026-10-08")}]
    )[venda_repository.COLUNAS])

    venda_repository.atualizar(completa=False)

    datas = pd.to_datetime(venda_repository.ler_csv(arquivo)["DATA"])   # formato único: não quebra
    assert list(datas.dt.strftime("%d/%m/%Y")) == ["02/01/2025", "08/10/2026"]
