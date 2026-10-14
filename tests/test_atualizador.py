from datetime import date, datetime

import pandas as pd

from core.repositories import arquivos_repository as arquivos_oracle
from core.services import atualizador_service as atualizador
from core.repositories import faturamento_repository as faturamento_data
from core.repositories import faturamento_diario_repository as faturamento_diario_data


# --- quando rodar ---

def test_ao_abrir_roda_completa_a_qualquer_hora():
    assert atualizador.proxima_acao(datetime(2026, 10, 6, 22, 0), None, None) == "completa"


def test_no_horario_roda_parcial_de_hora_em_hora():
    hoje = date(2026, 10, 6)
    agora = datetime(2026, 10, 6, 10, 0)

    assert atualizador.proxima_acao(agora, hoje, None) == "parcial"
    assert atualizador.proxima_acao(agora, hoje, ultima_parcial=9e18) is None


def test_a_noite_nao_roda():
    hoje = date(2026, 10, 6)

    assert atualizador.proxima_acao(datetime(2026, 10, 6, 20, 0), hoje, None) is None
    assert atualizador.proxima_acao(datetime(2026, 10, 7, 3, 0), hoje, None) is None


def test_primeiro_ciclo_do_dia_e_completo():
    ontem = date(2026, 10, 5)

    assert atualizador.proxima_acao(datetime(2026, 10, 6, 7, 0), ontem, None) == "completa"


def test_ao_abrir_so_faz_a_completa_se_ainda_nao_rodou_hoje():
    hoje = date(2026, 10, 13)

    # Já rodou hoje: ao abrir, a parcial (no horário).
    ultima_completa, ultima_parcial = atualizador.estado_inicial(hoje, hoje)
    assert atualizador.proxima_acao(datetime(2026, 10, 13, 10, 0), ultima_completa, ultima_parcial) == "parcial"

    # Rodou ontem (ou nunca): a completa, a qualquer hora.
    for dia in (date(2026, 10, 12), None):
        ultima_completa, ultima_parcial = atualizador.estado_inicial(hoje, dia)
        assert atualizador.proxima_acao(datetime(2026, 10, 13, 22, 0), ultima_completa, ultima_parcial) == "completa"


def test_janela_parcial_e_o_mes_anterior_e_o_atual():
    assert arquivos_oracle.inicio_da_janela_parcial(date(2026, 10, 6)) == date(2026, 9, 1)
    assert arquivos_oracle.inicio_da_janela_parcial(date(2026, 1, 15)) == date(2025, 12, 1)


# --- parcial junta o histórico do CSV com os meses novos do Oracle ---

def test_parcial_mensal_troca_so_os_meses_recentes(monkeypatch, tmp_path):
    arquivo = tmp_path / "mensal.csv"
    antigo = pd.DataFrame([
        {"CODFILIAL": 9, "ANO": 2026, "MES": 8, "VENDA_LIQ": 100.0},
        {"CODFILIAL": 9, "ANO": 2026, "MES": 9, "VENDA_LIQ": 1.0},   # vai ser refeito
    ])
    arquivos_oracle.gravar_csv(antigo, arquivo)
    novo = pd.DataFrame([
        {"CODFILIAL": 9, "ANO": 2026, "MES": 9, "VENDA_LIQ": 200.0},
        {"CODFILIAL": 9, "ANO": 2026, "MES": 10, "VENDA_LIQ": 30.0},
    ])
    pedidos = []
    monkeypatch.setattr(faturamento_data, "ARQUIVO_FATURAMENTO_MENSAL", arquivo)
    monkeypatch.setattr(faturamento_data, "inicio_da_janela_parcial", lambda: date(2026, 9, 1))
    monkeypatch.setattr(faturamento_data, "gerar_tabela", lambda desde=None: pedidos.append(desde) or novo)

    faturamento_data.atualizar(completa=False)

    resultado = arquivos_oracle.ler_csv(arquivo)
    assert pedidos == [date(2026, 9, 1)]
    assert list(zip(resultado["MES"], resultado["VENDA_LIQ"])) == [(8, 100.0), (9, 200.0), (10, 30.0)]


def test_parcial_diaria_troca_so_os_dias_recentes(monkeypatch, tmp_path):
    arquivo = tmp_path / "diario.csv"
    arquivos_oracle.gravar_csv(pd.DataFrame([
        {"CODFILIAL": 9, "DATA": "2026-08-31", "VENDA_LIQ": 10.0},
        {"CODFILIAL": 9, "DATA": "2026-09-02", "VENDA_LIQ": 1.0},    # vai ser refeito
    ]), arquivo)
    novo = pd.DataFrame([{"CODFILIAL": 9, "DATA": pd.Timestamp("2026-09-02"), "VENDA_LIQ": 20.0}])
    monkeypatch.setattr(faturamento_diario_data, "inicio_da_janela_parcial", lambda: date(2026, 9, 1))

    faturamento_diario_data._atualizar_arquivo(arquivo, lambda desde=None: novo, completa=False)

    resultado = arquivos_oracle.ler_csv(arquivo)
    assert list(resultado["DATA"]) == ["2026-08-31", "2026-09-02"]
    assert list(resultado["VENDA_LIQ"]) == [10.0, 20.0]


# --- leitura ---

def test_garantir_gera_na_hora_so_quando_o_arquivo_nao_existe(tmp_path):
    arquivo = tmp_path / "x.csv"
    chamadas = []

    def atualizar(completa):
        chamadas.append(completa)
        arquivos_oracle.gravar_csv(pd.DataFrame({"A": [1]}), arquivo)

    arquivos_oracle.garantir([arquivo], atualizar, "teste")
    arquivos_oracle.garantir([arquivo], atualizar, "teste")  # recém-gerado: não refaz

    assert chamadas == [True]


def test_gravar_nao_deixa_arquivo_temporario(tmp_path):
    arquivo = tmp_path / "x.csv"

    arquivos_oracle.gravar_csv(pd.DataFrame({"A": [1]}), arquivo)

    assert [caminho.name for caminho in tmp_path.iterdir()] == ["x.csv"]


def test_ler_csv_guarda_em_memoria_e_le_de_novo_quando_o_arquivo_muda(monkeypatch, tmp_path):
    arquivo = tmp_path / "x.csv"
    arquivos_oracle.gravar_csv(pd.DataFrame({"A": [1]}), arquivo)
    leituras = []
    ler_do_disco = pd.read_csv
    monkeypatch.setattr(
        arquivos_oracle.pd, "read_csv",
        lambda *args, **kwargs: leituras.append(1) or ler_do_disco(*args, **kwargs),
    )

    primeira = arquivos_oracle.ler_csv(arquivo)
    primeira.loc[0, "A"] = 99  # mexer na cópia não estraga a guardada
    segunda = arquivos_oracle.ler_csv(arquivo)
    arquivos_oracle.gravar_csv(pd.DataFrame({"A": [1, 2]}), arquivo)
    terceira = arquivos_oracle.ler_csv(arquivo)

    assert len(leituras) == 2
    assert segunda["A"].tolist() == [1]
    assert terceira["A"].tolist() == [1, 2]
