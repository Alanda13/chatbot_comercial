from src.variacao_utils import calcular_diferenca_percentual


def test_diferenca_e_percentual():
    assert calcular_diferenca_percentual(80, 100) == (20.0, 25.0)


def test_anterior_negativo_usa_valor_absoluto_no_percentual():
    assert calcular_diferenca_percentual(-100, 0) == (100.0, 100.0)


def test_anterior_zero_tem_diferenca_mas_nao_percentual():
    assert calcular_diferenca_percentual(0, 75) == (75.0, None)


def test_sem_um_dos_valores_nao_calcula_nada():
    assert calcular_diferenca_percentual(None, 10) == (None, None)
    assert calcular_diferenca_percentual(10, None) == (None, None)
