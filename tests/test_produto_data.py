import pandas as pd
import pytest

from core.motor import catalogo
from core.motor import orquestrador as orq
from core.repositories import produto_repository as produto_data


def _produtos():
    return pd.DataFrame([
        {"CODPROD": 95844, "PRODUTO": "VERGALHAO CA50 10,0MM RETO NERV 12M N",
         "GRUPO": "VERGALHÃO", "FAMILIA": "VERGALHÃO 10,0"},
        {"CODPROD": 95845, "PRODUTO": "VERGALHAO CA50 10,0MM 6M",
         "GRUPO": "VERGALHÃO", "FAMILIA": "VERGALHÃO 10,0"},
        {"CODPROD": 70001, "PRODUTO": "BARRA REDONDA A36 3/8 (TIPO VERGALHAO 10)",
         "GRUPO": "BARRA", "FAMILIA": "BARRA REDONDA A36 3/8"},
        {"CODPROD": 59025, "PRODUTO": "TELHA GALVALUME TRAP. 0,40X6000 MM IMP",
         "GRUPO": "TELHA", "FAMILIA": "TELHA GALVALUME TRAP. 0,40X6000 MM"},
        {"CODPROD": 59026, "PRODUTO": "TELHA PINTADA TRAP 0,40MM",
         "GRUPO": "TELHA", "FAMILIA": "TELHA PINTADA TRAP 0,40MM"},
        {"CODPROD": 1, "PRODUTO": "PRODUTO NOVO SEM PLANILHA",
         "GRUPO": produto_data.SEM_GRUPO, "FAMILIA": "PRODUTO NOVO SEM PLANILHA"},
    ])


@pytest.fixture
def produtos(monkeypatch):
    monkeypatch.setattr(produto_data, "carregar_produtos", _produtos)


def test_grupo_e_familia_pelo_nome(produtos):
    assert produto_data.resolver_grupos("telha") == ["TELHA"]
    assert produto_data.resolver_familias("vergalhão 10,0") == ["VERGALHÃO 10,0"]


def test_familia_com_varias_opcoes_pergunta(produtos):
    with pytest.raises(ValueError, match="mais de um"):
        produto_data.resolver_familias("telha")


def test_produto_pelo_nome_vira_a_familia(produtos):
    """'vergalhão 10' também aparece num produto de BARRA REDONDA, mas só
    a família VERGALHÃO 10,0 tem as palavras no nome — é ela."""
    assert sorted(produto_data.resolver_produtos("vergalhão 10")) == [95844, 95845]


def test_produto_pelo_codigo_e_so_ele(produtos):
    assert produto_data.resolver_produtos("95844") == [95844]
    with pytest.raises(ValueError):
        produto_data.resolver_produtos("999999")


def test_produto_em_familias_diferentes_pergunta(produtos):
    with pytest.raises(ValueError, match="mais de uma família"):
        produto_data.resolver_produtos("telha trap")


def test_montar_produtos_sem_planilha_fica_sem_grupo(monkeypatch):
    monkeypatch.setattr(produto_data, "_classificacao", lambda: pd.DataFrame(
        [{"CODPROD": 10, "GRUPO": "TELHA", "FAMILIA": "TELHA X"}]
    ))
    cadastro = pd.DataFrame([
        {"CODPROD": 10, "PRODUTO": "TELHA X 6M"}, {"CODPROD": 11, "PRODUTO": "ITEM NOVO"},
        {"CODPROD": 12, "PRODUTO": "NUNCA VENDIDO"},
    ])
    desconto = pd.DataFrame({"CODPROD": [10, 11]})

    produtos = produto_data._montar_produtos(cadastro, desconto).set_index("CODPROD")

    assert list(produtos.index) == [10, 11]
    assert produtos.loc[11, "GRUPO"] == produto_data.SEM_GRUPO
    assert produtos.loc[11, "FAMILIA"] == "ITEM NOVO"


def test_desconto_por_grupo_no_motor(monkeypatch, produtos):
    dados = pd.DataFrame([
        {"FILIAL": "TIMON", "ESTADO": "MA", "ANO": 2026, "MES": 9, "CODPROD": cod,
         "VALORDESC": desc, "VENDA_TABELA": 1000.0, "VENDA_BRUTA": 1000.0}
        for cod, desc in [(95844, 30.0), (95845, 10.0), (59025, 50.0)]
    ]).merge(_produtos(), on="CODPROD")
    monkeypatch.setitem(
        catalogo.INDICADORES["desconto"], "fontes_por_dimensao",
        {"produto": lambda: dados, "familia": lambda: dados, "grupo": lambda: dados},
    )

    resposta = orq.executar_consulta({
        "indicador": "desconto", "filtros": {"ano": [2026], "grupo": ["vergalhão"]},
    })

    assert resposta["resultados"][0]["valor_desconto"] == 40.0
    assert resposta["resultados"][0]["percentual_desconto"] == 2.0


def test_juntar_devolucao_desconta_e_conta_devolucao_sem_venda():
    from core.repositories.faturamento_repository import juntar_devolucao

    class Cursor:
        description = [("CODFILIAL",), ("ANO",), ("MES",), ("CODPROD",), ("VALOR_DEV",)]

        def execute(self, *args, **kwargs):
            pass

        def fetchall(self):
            return [(9, 2026, 9, 10, 100.0), (9, 2026, 9, 11, 50.0)]

    vendas = pd.DataFrame([
        {"CODFILIAL": 9, "ANO": 2026, "MES": 9, "CODPROD": 10,
         "VALORDESC": 5.0, "VENDA_TABELA": 1000.0, "VENDA_BRUTA": 1000.0},
    ])

    dados = juntar_devolucao(vendas, Cursor(), None, {"CODPROD": "CODPROD"}).set_index("CODPROD")

    assert dados.loc[10, "VENDA_LIQ"] == 900.0
    assert dados.loc[11, "VENDA_LIQ"] == -50.0
