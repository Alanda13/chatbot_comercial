import pandas as pd
import pytest

from core.repositories import filiais_repository as filiais


def test_padronizar_filiais_descarta_outras_e_soma_o_30_no_24():
    dados = pd.DataFrame({"X": [1, 2, 3, 4]}, index=[10, 11, 12, 13])
    codigos = pd.Series([9, 22, 30, 24], index=dados.index)

    resultado = filiais.padronizar_filiais(dados, codigos)

    assert list(resultado["X"]) == [1, 3, 4]
    assert list(resultado["FILIAL"]) == ["TIMON", "ARAGUAÍNA", "ARAGUAÍNA"]
    assert list(resultado["CODFILIAL"]) == [9, 24, 24]
    assert list(resultado["ESTADO"]) == ["MA", "TO", "TO"]


def test_listar_filiais_tem_18_lojas_sem_repetir_araguaina():
    lista = filiais.listar_filiais()

    assert len(lista) == 18
    assert lista.count("ARAGUAÍNA") == 1


@pytest.mark.parametrize(
    "digitado, esperado",
    [
        ("Timon", "TIMON"),
        ("FERRONORTE TIMON", "TIMON"),
        ("inox e aluminio", "INOX E ALUMINIO"),
        ("Santa Ines", "SANTA INÊS"),
        ("joao xxiii", "JOÃO XXIII"),
        ("Timor", "TIMON"),
    ],
)
def test_resolver_nome_filial(digitado, esperado):
    assert filiais.resolver_nome_filial(digitado) == esperado


@pytest.mark.parametrize(
    "digitado, esperado",
    [
        ("9", "TIMON"),
        (9, "TIMON"),
        ("filial 9", "TIMON"),
        ("codfilial 09", "TIMON"),
        ("código 24", "ARAGUAÍNA"),
        ("30", "ARAGUAÍNA"),
    ],
)
def test_resolver_nome_filial_por_codigo(digitado, esperado):
    assert filiais.resolver_nome_filial(digitado) == esperado


def test_resolver_nome_filial_codigo_fora_da_lista_gera_erro():
    with pytest.raises(ValueError):
        filiais.resolver_nome_filial("22")  # FN Atacado: fora da lista


def test_resolver_nome_filial_fora_da_lista_gera_erro():
    with pytest.raises(ValueError):
        filiais.resolver_nome_filial("FN Atacado")


def test_resolver_estado_aceita_sigla_e_nome():
    assert filiais.resolver_estado("MA") == "MA"
    assert filiais.resolver_estado("Maranhão") == "MA"
    assert filiais.resolver_estado("piaui") == "PI"

    with pytest.raises(ValueError):
        filiais.resolver_estado("Marte")
