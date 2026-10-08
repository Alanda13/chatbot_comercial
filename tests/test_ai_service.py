import json
from types import SimpleNamespace

import pytest

from core.services import ia_service as ai_service
from core.services.ia_service import _montar_historico_gemini
from core.exceptions import IAIndisponivelError


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


def test_formatar_historico_para_resposta_vazio():
    assert ai_service._formatar_historico_para_resposta(None) == (
        "Nenhuma mensagem anterior nesta conversa."
    )


def test_formatar_historico_para_resposta_formata_papeis():
    historico = [
        {"papel": "user", "conteudo": "Quantas toneladas em abril?"},
        {"papel": "assistant", "conteudo": "688,18 toneladas."},
    ]

    texto = ai_service._formatar_historico_para_resposta(historico)

    assert "Usuário: Quantas toneladas em abril?" in texto
    assert "Assistente: 688,18 toneladas." in texto


class _ModelsFalso:
    def __init__(self, texto_resposta):
        self._texto_resposta = texto_resposta
        self.chamadas = []

    def generate_content(self, model, contents, config=None):
        self.chamadas.append(contents)
        self.configuracoes = getattr(self, "configuracoes", []) + [config]
        return SimpleNamespace(text=self._texto_resposta)


class _ClienteRespostaFalso:
    def __init__(self, texto_resposta):
        self.models = _ModelsFalso(texto_resposta)


def test_gerar_resposta_final_inclui_historico_no_prompt(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "modelo-principal")
    monkeypatch.setenv("GEMINI_MODEL_FALLBACK", "modelo-reserva")

    cliente_falso = _ClienteRespostaFalso("resposta gerada")
    monkeypatch.setattr(
        ai_service, "criar_cliente_gemini", lambda: cliente_falso
    )

    historico = [
        {"papel": "user", "conteudo": "Quantas toneladas em abril?"},
        {"papel": "assistant", "conteudo": "688,18 toneladas."},
    ]

    resposta = ai_service.gerar_resposta_final(
        pergunta="e em julho?",
        nome_ferramenta="consultar_indicadores_faturamento",
        resultado={"encontrado": True, "toneladas": 700.0},
        historico=historico,
    )

    assert resposta == "resposta gerada"
    prompt_enviado = cliente_falso.models.chamadas[0]
    assert "Quantas toneladas em abril?" in prompt_enviado
    assert "688,18 toneladas." in prompt_enviado


def test_gerar_resposta_final_sem_historico_nao_quebra(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "modelo-principal")
    monkeypatch.setenv("GEMINI_MODEL_FALLBACK", "modelo-reserva")

    cliente_falso = _ClienteRespostaFalso("resposta gerada")
    monkeypatch.setattr(
        ai_service, "criar_cliente_gemini", lambda: cliente_falso
    )

    resposta = ai_service.gerar_resposta_final(
        pergunta="Qual o faturamento de Timon em julho de 2025?",
        nome_ferramenta="consultar_indicadores_faturamento",
        resultado={"encontrado": True, "faturamento": 100.0},
    )

    assert resposta == "resposta gerada"


def test_calendario_recente_da_a_data_de_cada_dia():
    """'Sexta da semana passada' em 05/10/2026 = 02/10/2026 — sem isso a IA
    consultava a semana inteira e dizia que era a sexta."""
    from datetime import date
    from core.services.ia_service import calendario_recente

    texto = calendario_recente(date(2026, 10, 5))

    assert "Hoje é segunda-feira, 05/10/2026." in texto
    assert "Semana passada: segunda-feira 28/09/2026" in texto
    assert "sexta-feira 02/10/2026" in texto


def test_resposta_final_liga_execucao_de_codigo_e_cai_pro_jeito_antigo_se_falhar(monkeypatch):
    """
    Com "executar código", as contas de análise (% de grupo, média,
    correlação) são feitas por Python. Se o recurso falhar (outro modelo,
    outra chave), a resposta sai sem ele em vez de dar erro.
    """
    from core.services import ia_service as ai_service

    class ModelsSemCodigo(_ModelsFalso):
        def generate_content(self, model, contents, config=None):
            if config is not None:
                raise RuntimeError("code execution indisponível")
            return super().generate_content(model, contents, config)

    modelos = ModelsSemCodigo("resposta sem contas")
    monkeypatch.setattr(
        ai_service, "criar_cliente_gemini", lambda: SimpleNamespace(models=modelos)
    )

    texto = ai_service.gerar_resposta_final(
        pergunta="as filiais com nps acima de 90 dão mais desconto?",
        nome_ferramenta="consultar_dados_comerciais",
        resultado={"resultados": []},
    )

    assert texto == "resposta sem contas"
    assert modelos.configuracoes == [None]


def test_resposta_com_numero_inventado_nunca_chega_a_tela(monkeypatch):
    """O código calculou 2,70%, mas o texto sempre sai com 2,75% (caso
    real): depois das tentativas, não mostra número nenhum."""
    from core.services import ia_service as ai_service

    modelos = _ModelsFalso("Sem Parnaíba, o grupo cai para 2,75%.")
    monkeypatch.setattr(
        ai_service, "criar_cliente_gemini", lambda: SimpleNamespace(models=modelos)
    )

    texto = ai_service.gerar_resposta_final(
        pergunta="as filiais com nps acima de 90 dão mais desconto?",
        nome_ferramenta="consultar_dados_comerciais",
        resultado={"resultados": [{"filial": "PARNAIBA", "percentual_desconto": 6.5931}]},
    )

    assert "2,75" not in texto
    assert texto == ai_service._RESPOSTA_SEM_NUMEROS_CONFERIDOS


def test_percentuais_vao_pra_ia_com_duas_casas_como_na_tabela():
    from core.services.ia_service import _percentuais_como_na_tabela

    dados = {"resultados": [{"percentual_desconto": 5.6574, "valor_desconto": 214235.1934}],
             "total": {"percentual_desconto": 0.0042}}

    saida = _percentuais_como_na_tabela(dados)

    assert saida["resultados"][0] == {"percentual_desconto": 5.66, "valor_desconto": 214235.1934}
    assert saida["total"]["percentual_desconto"] == 0.0042
