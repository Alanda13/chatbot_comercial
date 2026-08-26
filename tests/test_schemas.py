import pytest
from pydantic import ValidationError

from src.schemas import SolicitacaoFerramenta


def test_solicitacao_valida_para_executar_ferramenta():
    solicitacao = SolicitacaoFerramenta.model_validate(
        {
            "acao": "executar_ferramenta",
            "ferramenta": "consultar_indicadores_nps",
            "argumentos": {"filiais": ["Timon"]},
            "mensagem": None,
        }
    )

    assert solicitacao.ferramenta == "consultar_indicadores_nps"
    assert solicitacao.argumentos == {"filiais": ["Timon"]}


def test_solicitacao_valida_sem_argumentos_usa_dict_vazio():
    solicitacao = SolicitacaoFerramenta.model_validate(
        {"acao": "fora_do_escopo", "mensagem": "Fora do escopo."}
    )

    assert solicitacao.argumentos == {}


def test_acao_invalida_gera_erro_de_validacao():
    with pytest.raises(ValidationError):
        SolicitacaoFerramenta.model_validate({"acao": "fazer_cafe"})


def test_acao_ausente_gera_erro_de_validacao():
    with pytest.raises(ValidationError):
        SolicitacaoFerramenta.model_validate({})
