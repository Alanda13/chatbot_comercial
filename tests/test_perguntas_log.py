from src import perguntas_log


def _usar_banco_temporario(tmp_path, monkeypatch):
    monkeypatch.setattr(
        perguntas_log,
        "ARQUIVO_LOG",
        tmp_path / "perguntas.db",
    )


def test_registrar_e_contar_perguntas(tmp_path, monkeypatch):
    _usar_banco_temporario(tmp_path, monkeypatch)

    perguntas_log.registrar_pergunta("Qual o faturamento de Timon?")
    perguntas_log.registrar_pergunta("Qual o NPS geral?")

    assert perguntas_log.contar_perguntas_registradas() == 2


def test_registrar_pergunta_vazia_nao_conta(tmp_path, monkeypatch):
    _usar_banco_temporario(tmp_path, monkeypatch)

    perguntas_log.registrar_pergunta("")
    perguntas_log.registrar_pergunta("   ")

    assert perguntas_log.contar_perguntas_registradas() == 0


def test_perguntas_frequentes_agrupa_por_texto_normalizado(
    tmp_path, monkeypatch
):
    _usar_banco_temporario(tmp_path, monkeypatch)

    perguntas_log.registrar_pergunta("Qual o faturamento de Timon?")
    perguntas_log.registrar_pergunta("  qual o faturamento de timon?  ")
    perguntas_log.registrar_pergunta("Qual o NPS geral?")

    resultado = perguntas_log.obter_perguntas_frequentes(limite=5)

    quantidades = {item["pergunta"]: item["quantidade"] for item in resultado}
    assert quantidades["Qual o faturamento de Timon?"] == 2
    assert quantidades["Qual o NPS geral?"] == 1


def test_perguntas_frequentes_respeita_limite(tmp_path, monkeypatch):
    _usar_banco_temporario(tmp_path, monkeypatch)

    for numero in range(10):
        perguntas_log.registrar_pergunta(f"Pergunta {numero}")

    resultado = perguntas_log.obter_perguntas_frequentes(limite=3)

    assert len(resultado) == 3
