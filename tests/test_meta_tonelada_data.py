import pandas as pd
import pytest

from core.repositories import meta_tonelada_repository as mtd


def _dados_teste():
    return pd.DataFrame(
        [
            {
                "FILIAL": "COMERCIAL FERRONORTE LTDA-F09-TIMON",
                "ANO": 2025,
                "MES": 1,
                "RCA": "AURORA ANDRADE-F01",
                "Meta Tonelada - Filial": 622.03,
                "Meta Tonelada - RCA": 175.03,
            },
            {
                "FILIAL": "COMERCIAL FERRONORTE LTDA-F01-MATRIZ",
                "ANO": 2025,
                "MES": 1,
                "RCA": "JUNIOR PEREIRA-F01",
                "Meta Tonelada - Filial": 400.00,
                "Meta Tonelada - RCA": 100.00,
            },
        ]
    )


def test_carregar_meta_tonelada_padroniza_filiais(monkeypatch, tmp_path):
    """O código da filial vem do nome ("-F09-") e o nome vira o padrão."""
    arquivo = tmp_path / "meta_tonelada.csv"
    arquivo.write_text(
        "FILIAL;ANO;MES;RCA;Meta Tonelada - Filial;Meta Tonelada - RCA\n"
        "COMERCIAL FERRONORTE LTDA-F09-TIMON;2025;1;A-F09;622.03;175.03\n"
        "FERROLESTE LTDA-F08-FL JXXIII;2025;1;B-F08;100.0;50.0\n"
        "COMERCIAL FERRONORTE LTDA-F99-OUTRA;2025;1;C-F99;1.0;1.0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mtd, "ARQUIVO_META_TONELADA", arquivo)

    dados = mtd.carregar_meta_tonelada()

    assert list(dados["FILIAL"]) == ["TIMON", "JOÃO XXIII"]
    assert list(dados["ESTADO"]) == ["MA", "PI"]


def test_construir_lista_rca_tonelada(monkeypatch):
    monkeypatch.setattr(
        mtd, "carregar_meta_tonelada", lambda: _dados_teste()
    )

    lista = mtd.construir_lista_rca_tonelada()

    nomes = {item["nome"] for item in lista}
    assert nomes == {"AURORA ANDRADE-F01", "JUNIOR PEREIRA-F01"}


def test_resolver_nomes_rca_tonelada_encontra_unico(monkeypatch):
    monkeypatch.setattr(
        mtd, "carregar_meta_tonelada", lambda: _dados_teste()
    )

    assert mtd.resolver_nomes_rca_tonelada("Aurora Andrade") == [
        "AURORA ANDRADE-F01"
    ]


def test_resolver_nomes_rca_tonelada_nao_encontrado(monkeypatch):
    monkeypatch.setattr(
        mtd, "carregar_meta_tonelada", lambda: _dados_teste()
    )

    with pytest.raises(ValueError):
        mtd.resolver_nomes_rca_tonelada("Vendedor Inexistente Xyz")


def test_resolver_nomes_rca_tonelada_ambiguo_sem_filial_soma(monkeypatch):
    monkeypatch.setattr(
        mtd,
        "construir_lista_rca_tonelada",
        lambda: [
            {"nome": "JOAO SILVA-F01", "filial": "FILIAL A"},
            {"nome": "JOAO SILVA-F02", "filial": "FILIAL B"},
        ],
    )

    nomes = mtd.resolver_nomes_rca_tonelada("Joao Silva")

    assert sorted(nomes) == ["JOAO SILVA-F01", "JOAO SILVA-F02"]


def test_resolver_nomes_rca_tonelada_ambiguo_com_filial_desambigua(
    monkeypatch,
):
    monkeypatch.setattr(
        mtd,
        "construir_lista_rca_tonelada",
        lambda: [
            {"nome": "JOAO SILVA-F01", "filial": "FILIAL A"},
            {"nome": "JOAO SILVA-F02", "filial": "FILIAL B"},
        ],
    )

    nomes = mtd.resolver_nomes_rca_tonelada(
        "Joao Silva",
        filiais=["FILIAL B"],
    )

    assert nomes == ["JOAO SILVA-F02"]
