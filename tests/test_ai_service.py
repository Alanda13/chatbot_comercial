import json
from types import SimpleNamespace

import pytest

from src import ai_service
from src.ai_service import _montar_historico_gemini
from src.exceptions import IAIndisponivelError


class _ChatFalso:
    def __init__(self, texto_resposta):
        self._texto_resposta = texto_resposta

    def send_message(self, mensagem, config=None):
        return SimpleNamespace(text=self._texto_resposta)


class _ChatsFalso:
    def __init__(self, textos_por_modelo):
        self._textos_por_modelo = textos_por_modelo

    def create(self, model, history=None, config=None):
        return _ChatFalso(self._textos_por_modelo[model])


class _ClienteFalso:
    def __init__(self, textos_por_modelo):
        self.chats = _ChatsFalso(textos_por_modelo)


def _preparar_cliente_falso(monkeypatch, textos_por_modelo):
    monkeypatch.setenv("GEMINI_MODEL", "modelo-principal")
    monkeypatch.setenv("GEMINI_MODEL_FALLBACK", "modelo-reserva")
    monkeypatch.setattr(
        ai_service,
        "criar_cliente_gemini",
        lambda: _ClienteFalso(textos_por_modelo),
    )


def test_interpretar_pergunta_tenta_proximo_modelo_se_json_invalido(
    monkeypatch,
):
    _preparar_cliente_falso(
        monkeypatch,
        {
            "modelo-principal": "isso não é json",
            "modelo-reserva": json.dumps(
                {"acao": "fora_do_escopo", "mensagem": "ok"}
            ),
        },
    )

    resultado = ai_service.interpretar_pergunta("qualquer coisa")

    assert resultado.acao == "fora_do_escopo"


def test_interpretar_pergunta_tenta_proximo_modelo_se_fora_do_contrato(
    monkeypatch,
):
    _preparar_cliente_falso(
        monkeypatch,
        {
            "modelo-principal": json.dumps({"acao": "nao_existe"}),
            "modelo-reserva": json.dumps(
                {"acao": "fora_do_escopo", "mensagem": "ok"}
            ),
        },
    )

    resultado = ai_service.interpretar_pergunta("qualquer coisa")

    assert resultado.acao == "fora_do_escopo"


def test_interpretar_pergunta_falha_se_todos_os_modelos_falharem(
    monkeypatch,
):
    _preparar_cliente_falso(
        monkeypatch,
        {
            "modelo-principal": "isso não é json",
            "modelo-reserva": "isso também não é json",
        },
    )

    with pytest.raises(IAIndisponivelError):
        ai_service.interpretar_pergunta("qualquer coisa")


def test_montar_historico_mapeia_papel_assistant_para_model():
    historico = [
        {"papel": "user", "conteudo": "Qual o NPS de Timon?"},
        {"papel": "assistant", "conteudo": "O NPS de Timon é 80."},
    ]

    conteudos = _montar_historico_gemini(historico)

    assert conteudos[0].role == "user"
    assert conteudos[0].parts[0].text == "Qual o NPS de Timon?"
    assert conteudos[1].role == "model"
    assert conteudos[1].parts[0].text == "O NPS de Timon é 80."


def test_montar_historico_vazio():
    assert _montar_historico_gemini([]) == []
