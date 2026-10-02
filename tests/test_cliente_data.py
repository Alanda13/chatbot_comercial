import pandas as pd
import pytest

from src import catalogo
from src import cliente_data
from src import orquestrador as orq


def _clientes():
    return pd.DataFrame(
        [
            {"CODCLI": 202334, "CLIENTE": "MATEUS SUPERMERCADOS S A",
             "FANTASIA": "MIX MATEUS", "CNPJ": "03.995.515/0159-46",
             "CIDADE": "SAO LUIS", "UF": "MA", "EMPRESA": "03995515",
             "NOME_EMPRESA": "MATEUS SUPERMERCADOS S A",
             "CNPJ_EMPRESA": "03.995.515", "VENDA_TOTAL": 900.0},
            {"CODCLI": 191385, "CLIENTE": "MATEUS SUPERMERCADOS SA",
             "FANTASIA": "ELETRO MATEUS", "CNPJ": "03.995.515/0034-25",
             "CIDADE": "IMPERATRIZ", "UF": "MA", "EMPRESA": "03995515",
             "NOME_EMPRESA": "MATEUS SUPERMERCADOS S A",
             "CNPJ_EMPRESA": "03.995.515", "VENDA_TOTAL": 800.0},
            {"CODCLI": 500, "CLIENTE": "ARMAZEM MATEUS S A",
             "FANTASIA": None, "CNPJ": "23.439.441/0001-10",
             "CIDADE": "SAO LUIS", "UF": "MA", "EMPRESA": "23439441",
             "NOME_EMPRESA": "ARMAZEM MATEUS S A",
             "CNPJ_EMPRESA": "23.439.441", "VENDA_TOTAL": 100.0},
            {"CODCLI": 1, "CLIENTE": "CONSUMIDOR FINAL", "FANTASIA": None,
             "CNPJ": "111.111.111-11", "CIDADE": "TERESINA", "UF": "PI",
             "EMPRESA": "CLI1", "NOME_EMPRESA": "CONSUMIDOR FINAL",
             "CNPJ_EMPRESA": "111.111.111-11", "VENDA_TOTAL": 50.0},
        ]
    )


@pytest.fixture
def clientes(monkeypatch):
    monkeypatch.setattr(cliente_data, "carregar_clientes", _clientes)


# --- empresa = início do CNPJ ---

@pytest.mark.parametrize(
    "cnpj, esperado",
    [
        ("03.995.515/0159-46", "03995515"),
        ("03995515003425", "03995515"),
        ("111.111.111-11", "11111111111"),   # CPF: junta a mesma pessoa
        ("000.000.000-00", "CLI7"),          # CPF zerado: fica sozinho
        ("00000000000000", "CLI7"),          # CNPJ inválido
        (None, "CLI7"),
    ],
)
def test_identificar_empresa(cnpj, esperado):
    assert cliente_data.identificar_empresa(7, cnpj) == esperado


# --- busca pelo nome / código ---

def test_nome_de_uma_empresa_so_junta_todas_as_lojas(clientes):
    assert cliente_data.resolver_empresas("mix mateus") == ["03995515"]
    assert sorted(cliente_data.resolver_codigos_cliente("supermercados")) == [
        191385, 202334,
    ]


def test_nome_de_varias_empresas_pede_para_escolher(clientes):
    with pytest.raises(ValueError) as erro:
        cliente_data.resolver_empresas("Mateus")

    mensagem = str(erro.value)
    assert "MATEUS SUPERMERCADOS S A (CNPJ 03.995.515" in mensagem
    assert "ARMAZEM MATEUS S A (CNPJ 23.439.441" in mensagem
    # a que mais compra vem primeiro
    assert mensagem.index("03.995.515") < mensagem.index("23.439.441")


def test_inicio_do_cnpj_e_codigo(clientes):
    assert cliente_data.resolver_empresas("03.995.515") == ["03995515"]
    assert cliente_data.resolver_empresas("23439441000110") == ["23439441"]
    assert cliente_data.resolver_empresas("CLI1") == ["CLI1"]
    # código do cliente: a empresa daquela loja
    assert cliente_data.resolver_empresas("191385") == ["03995515"]
    # no filtro "cliente", o código é UMA loja só
    assert cliente_data.resolver_codigos_cliente(191385) == [191385]


def test_cliente_inexistente(clientes):
    with pytest.raises(ValueError):
        cliente_data.resolver_codigos_cliente(999999)
    with pytest.raises(ValueError):
        cliente_data.resolver_empresas("Padaria Inexistente")


# --- motor: arquivo de cliente, nome/CNPJ/cidade e total ---

def _desconto_cliente():
    vendas = pd.DataFrame(
        [
            {"FILIAL": "TIMON", "ESTADO": "MA", "COD_RCA": 10, "COD_SUPERVISOR": 1,
             "MES": 8, "ANO": 2026, "CODCLI": 202334,
             "VALORDESC": 30.0, "VENDA_TABELA": 300.0},
            {"FILIAL": "LOURIVAL", "ESTADO": "PI", "COD_RCA": 20, "COD_SUPERVISOR": 2,
             "MES": 8, "ANO": 2026, "CODCLI": 191385,
             "VALORDESC": 10.0, "VENDA_TABELA": 200.0},
            {"FILIAL": "TIMON", "ESTADO": "MA", "COD_RCA": 10, "COD_SUPERVISOR": 1,
             "MES": 8, "ANO": 2026, "CODCLI": 500,
             "VALORDESC": 5.0, "VENDA_TABELA": 100.0},
        ]
    )
    return vendas.merge(_clientes(), on="CODCLI")


@pytest.fixture
def motor(monkeypatch, clientes):
    def mensal_sem_cliente():
        raise AssertionError("pergunta por cliente não deve ler o arquivo mensal")

    monkeypatch.setitem(catalogo.INDICADORES["desconto"], "carregar", mensal_sem_cliente)
    monkeypatch.setitem(
        catalogo.INDICADORES["desconto"], "fontes_por_dimensao",
        {"cliente": _desconto_cliente, "empresa": _desconto_cliente},
    )


def test_empresa_soma_as_lojas_e_por_loja_traz_nome_cnpj_cidade(motor):
    resultado = orq.executar_consulta({
        "indicador": "desconto",
        "filtros": {"ano": [2026], "empresa": ["03.995.515"]},
        "agrupar_por": ["cliente"],
        "ordenar_por": {"campo": "valor_desconto", "limite": 1},
    })

    assert resultado["resultados"] == [
        {
            "cliente": 202334, "valor_desconto": 30.0, "faturamento_tabela": 300.0,
            "cliente_nome": "MATEUS SUPERMERCADOS S A",
            "cnpj": "03.995.515/0159-46", "cidade": "SAO LUIS",
            "percentual_desconto": 10.0,
        }
    ]
    # total das 2 lojas, mesmo com o limite mostrando só 1
    assert resultado["total_de_todas_as_linhas"] == {
        "valor_desconto": 40.0, "faturamento_tabela": 500.0,
        "percentual_desconto": 8.0, "quantidade_de_linhas": 2,
        "quantidade_por_dimensao": {"cliente": 2},
    }
    # nome oficial da empresa filtrada, pra resposta citar
    assert resultado["itens_filtrados"] == {
        "empresa": [{
            "empresa": "03995515", "empresa_nome": "MATEUS SUPERMERCADOS S A",
            "cnpj_empresa": "03.995.515",
        }]
    }


def test_desconto_sem_periodo_pede_o_periodo(motor):
    # sem período somaria desde 2020 (ex: Mateus em Timon: R$ 205 mil,
    # quase tudo de 2020) — a IA tem que perguntar
    with pytest.raises(orq.ConsultaInvalida, match="Falta o período"):
        orq.executar_consulta({
            "indicador": "desconto", "filtros": {"empresa": ["03995515"]},
        })


def test_ranking_por_empresa_e_filial_da_venda(motor):
    resultado = orq.executar_consulta({
        "indicador": "desconto",
        "filtros": {"ano": [2026], "filial": ["Timon"]},
        "agrupar_por": ["empresa"],
        "ordenar_por": {"campo": "valor_desconto"},
    })

    # Lourival vendeu para a loja de Imperatriz — não entra em Timon
    assert [
        (linha["empresa_nome"], linha["valor_desconto"])
        for linha in resultado["resultados"]
    ] == [("MATEUS SUPERMERCADOS S A", 30.0), ("ARMAZEM MATEUS S A", 5.0)]


def test_n_maiores_grupos_e_principais_de_cada(motor, monkeypatch):
    # RCAs inventados não têm meta cadastrada (regra do agrupamento por RCA)
    monkeypatch.setitem(catalogo.INDICADORES["desconto"], "rca_requer_meta_cadastrada", False)
    # RCA 10 (Timon) deu 35 no total (30 + 5); RCA 20 deu 10. O maior PAR
    # sozinho não decide: o ranking é pelo total de cada RCA.
    resultado = orq.executar_consulta({
        "indicador": "desconto",
        "filtros": {"ano": [2026]},
        "agrupar_por": ["rca", "cliente"],
        "ordenar_por": {
            "campo": "valor_desconto", "por": "rca", "limite_grupos": 1, "limite": 1,
        },
    })

    assert [g["rca"] for g in resultado["totais_por_grupo"]] == [10]
    assert resultado["totais_por_grupo"][0]["valor_desconto"] == 35.0
    assert [(l["rca"], l["cliente"]) for l in resultado["resultados"]] == [(10, 202334)]


def test_por_precisa_estar_no_agrupamento(motor):
    with pytest.raises(orq.ConsultaInvalida, match="agrupar_por"):
        orq.executar_consulta({
            "indicador": "desconto", "filtros": {"ano": [2026]},
            "agrupar_por": ["cliente"],
            "ordenar_por": {"campo": "valor_desconto", "por": "rca"},
        })


def test_sem_limite_por_grupo_mantem_meses_em_ordem_e_variacao_em_reais(monkeypatch):
    """
    "Histórico mês a mês dos maiores RCAs": os meses ficam em ordem
    (antes vinham do maior desconto pro menor) e a variação é do desconto
    em R$ — não do % (9,05% → 9,07% = "+0,22%" escondia uma queda de R$
    115 mil pra R$ 19 mil).
    """
    dados = pd.DataFrame(
        [
            {"FILIAL": "TIMON", "ESTADO": "MA", "COD_RCA": 10, "COD_SUPERVISOR": 1,
             "MES": mes, "ANO": 2026, "VALORDESC": desconto, "VENDA_TABELA": tabela}
            for mes, desconto, tabela in [(5, 100.0, 1000.0), (6, 20.0, 200.0), (7, 50.0, 1000.0)]
        ]
    )
    monkeypatch.setitem(catalogo.INDICADORES["desconto"], "carregar", lambda: dados)
    monkeypatch.setitem(catalogo.INDICADORES["desconto"], "rca_requer_meta_cadastrada", False)

    resultado = orq.executar_consulta({
        "indicador": "desconto",
        "filtros": {"ano": [2026]},
        "agrupar_por": ["rca", "mes"],
        "ordenar_por": {"campo": "valor_desconto", "por": "rca", "limite_grupos": 3},
    })["resultados"]

    assert [linha["mes"] for linha in resultado] == [5, 6, 7]
    # junho: % igual a maio (10%), mas o desconto caiu de 100 pra 20
    assert resultado[1]["percentual_mes_anterior"] == -80.0
