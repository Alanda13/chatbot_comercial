from src.ai_service import _montar_historico_gemini


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
