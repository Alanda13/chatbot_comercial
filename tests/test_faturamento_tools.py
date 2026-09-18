import pytest

from src import faturamento_tools as ft


def test_executar_verificar_rca_sem_rca_gera_erro():
    with pytest.raises(ValueError):
        ft.executar_verificar_rca({})


def test_executar_verificar_rca_repassa_pro_data_layer(monkeypatch):
    chamadas = []

    monkeypatch.setattr(
        ft,
        "resolver_nome_filial",
        lambda nome: "FERRONORTE TIMON",
    )

    def fake_verificar(nome_ou_codigo, filiais=None):
        chamadas.append((nome_ou_codigo, filiais))
        return {"encontrado": False, "mensagem": "não encontrado"}

    monkeypatch.setattr(ft, "verificar_rca", fake_verificar)

    resultado = ft.executar_verificar_rca(
        {"rca": "4567", "filiais": ["Timon"]}
    )

    assert chamadas == [("4567", ["FERRONORTE TIMON"])]
    assert resultado["encontrado"] is False
