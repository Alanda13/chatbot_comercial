from datetime import datetime

import pytest

from src import nps_data


class _CursorFalso:
    def __init__(self, registros):
        self._registros = registros

    def execute(self, consulta):
        pass

    def fetchall(self):
        return self._registros

    def close(self):
        pass


class _ConexaoFalsa:
    def __init__(self, registros):
        self._registros = registros

    def cursor(self):
        return _CursorFalso(self._registros)

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _limpar_cache():
    nps_data._cache.update({"quando": 0.0, "dados": None})
    yield
    nps_data._cache.update({"quando": 0.0, "dados": None})


def _carregar_com(monkeypatch, registros):
    monkeypatch.setattr(
        nps_data, "get_connection", lambda: _ConexaoFalsa(registros)
    )
    return nps_data.carregar_avaliacoes_nps()


def test_carregar_classifica_promotor_neutro_detrator(monkeypatch):
    dados = _carregar_com(
        monkeypatch,
        [
            (9, datetime(2025, 7, 31, 23, 59), "10"),
            (9, datetime(2025, 7, 1, 8, 0), "9"),
            (9, datetime(2025, 7, 2, 8, 0), "8"),
            (9, datetime(2025, 7, 3, 8, 0), "7"),
            (9, datetime(2025, 7, 4, 8, 0), "6"),
            (9, datetime(2025, 7, 5, 8, 0), "0"),
        ],
    )

    assert list(dados["PROMOTOR"]) == [1, 1, 0, 0, 0, 0]
    assert list(dados["NEUTRO"]) == [0, 0, 1, 1, 0, 0]
    assert list(dados["DETRATOR"]) == [0, 0, 0, 0, 1, 1]
    assert dados["RESPOSTA"].sum() == 6


def test_carregar_ignora_notas_invalidas_e_normaliza_data_e_filial(monkeypatch):
    dados = _carregar_com(
        monkeypatch,
        [
            (9, datetime(2025, 7, 31, 23, 59), "10"),
            (9, datetime(2025, 7, 1, 8, 0), ""),
            (9, datetime(2025, 7, 1, 9, 0), "11"),
            (9, datetime(2025, 7, 1, 9, 0), "abc"),
        ],
    )

    assert len(dados) == 1
    assert dados.iloc[0]["FILIAL"] == "TIMON"
    # A hora é descartada — filtrar até 31/07 precisa incluir 23:59.
    assert dados.iloc[0]["DATA"] == datetime(2025, 7, 31)
    assert (dados.iloc[0]["MES"], dados.iloc[0]["ANO"]) == (7, 2025)


def test_carregar_reaproveita_leitura_recente(monkeypatch):
    chamadas = []

    def conexao():
        chamadas.append(1)
        return _ConexaoFalsa([(9, datetime(2025, 1, 1), "10")])

    monkeypatch.setattr(nps_data, "get_connection", conexao)

    nps_data.carregar_avaliacoes_nps()
    nps_data.carregar_avaliacoes_nps()

    assert len(chamadas) == 1


def test_carregar_descarta_filiais_fora_da_lista(monkeypatch):
    dados = _carregar_com(
        monkeypatch,
        [
            (9, datetime(2025, 7, 1), "10"),
            (51, datetime(2025, 7, 1), "10"),
        ],
    )

    assert list(dados["FILIAL"]) == ["TIMON"]
