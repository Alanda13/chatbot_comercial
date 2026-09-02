from src.filial_utils import (
    encontrar_filial_mais_proxima,
    normalizar_nome_filial,
)


def test_normalizar_remove_prefixos_e_acentos():
    assert normalizar_nome_filial("Filial Ferronorte de Timon") == "timon"


def test_normalizar_ignora_case_espacos_e_acentos():
    assert normalizar_nome_filial("  SANTA   Inês  ") == "santa ines"


def test_encontrar_filial_mais_proxima_correspondencia_direta():
    opcoes = ["FERRONORTE TIMON", "FERRONORTE PICOS"]

    resultado = encontrar_filial_mais_proxima(
        normalizar_nome_filial("Timon"),
        opcoes,
    )

    assert resultado == "FERRONORTE TIMON"


def test_encontrar_filial_mais_proxima_aceita_erro_de_digitacao():
    opcoes = ["FERRONORTE TIMON", "FERRONORTE PICOS"]

    resultado = encontrar_filial_mais_proxima(
        normalizar_nome_filial("Timor"),
        opcoes,
    )

    assert resultado == "FERRONORTE TIMON"


def test_encontrar_filial_mais_proxima_nao_confunde_nomes_parecidos():
    # "matriz" e "imperatriz" compartilham várias letras (ratio 0.75)
    # mas são filiais completamente diferentes — não pode aceitar
    # esse tipo de coincidência como correspondência válida.
    opcoes = ["FERRONORTE IMPERATRIZ", "FERRONORTE TIMON"]

    resultado = encontrar_filial_mais_proxima(
        normalizar_nome_filial("Matriz"),
        opcoes,
    )

    assert resultado is None


def test_encontrar_filial_mais_proxima_sem_correspondencia_aceitavel():
    opcoes = ["FERRONORTE TIMON"]

    resultado = encontrar_filial_mais_proxima(
        normalizar_nome_filial("Marte"),
        opcoes,
    )

    assert resultado is None


def test_encontrar_filial_mais_proxima_lista_vazia():
    resultado = encontrar_filial_mais_proxima(
        normalizar_nome_filial("Timon"),
        [],
    )

    assert resultado is None
