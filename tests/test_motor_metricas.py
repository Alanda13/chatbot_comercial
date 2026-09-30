from src import motor_metricas as mm


def test_calcular_atingimento_meta():
    assert mm.calcular_atingimento_meta(80000, 100000) == 80.0


def test_calcular_atingimento_meta_sem_meta_retorna_none():
    assert mm.calcular_atingimento_meta(80000, 0) is None
    assert mm.calcular_atingimento_meta(80000, None) is None


def test_calcular_desconto():
    assert mm.calcular_desconto(100000, 90000) == 10.0


def test_calcular_desconto_sem_faturamento_tabela_retorna_none():
    assert mm.calcular_desconto(0, 90000) is None


def test_calcular_inadimplencia():
    assert mm.calcular_inadimplencia(5000, 100000) == 5.0


def test_calcular_inadimplencia_sem_faturamento_liquido_retorna_none():
    assert mm.calcular_inadimplencia(5000, 0) is None


def test_calcular_crescimento():
    assert mm.calcular_crescimento(atual=110, anterior=100) == 10.0


def test_calcular_crescimento_sem_anterior_retorna_none():
    assert mm.calcular_crescimento(atual=110, anterior=0) is None
    assert mm.calcular_crescimento(atual=110, anterior=None) is None


def test_calcular_nps():
    # 60 promotores, 30 neutros, 10 detratores, em 100 respostas.
    assert mm.calcular_nps(60, 10, 100) == 50.0


def test_calcular_nps_pode_ser_negativo():
    assert mm.calcular_nps(10, 30, 100) == -20.0


def test_calcular_nps_sem_respostas_retorna_none():
    assert mm.calcular_nps(0, 0, 0) is None
    assert mm.calcular_nps(0, 0, None) is None


def test_calcular_valor_faltante():
    assert mm.calcular_valor_faltante(meta=100000, realizado=80000) == 20000.0


def test_calcular_valor_faltante_meta_superada_nao_fica_negativo():
    assert mm.calcular_valor_faltante(meta=80000, realizado=100000) == 0.0


def test_calcular_valor_faltante_sem_dado_retorna_none():
    assert mm.calcular_valor_faltante(None, 80000) is None
    assert mm.calcular_valor_faltante(100000, None) is None


def test_calcular_necessidade_diaria():
    assert mm.calcular_necessidade_diaria(20000, 10) == 2000.0


def test_calcular_necessidade_diaria_sem_dias_restantes_retorna_none():
    assert mm.calcular_necessidade_diaria(20000, 0) is None
    assert mm.calcular_necessidade_diaria(20000, None) is None


def test_calcular_participacao():
    assert mm.calcular_participacao(25000, 100000) == 25.0


def test_calcular_participacao_sem_total_retorna_none():
    assert mm.calcular_participacao(25000, 0) is None


def test_formulas_registradas_batem_com_as_funcoes():
    assert mm.FORMULAS["calcular_atingimento_meta"] is mm.calcular_atingimento_meta
    assert mm.FORMULAS["calcular_desconto"] is mm.calcular_desconto
    assert mm.FORMULAS["calcular_inadimplencia"] is mm.calcular_inadimplencia
    assert mm.FORMULAS["calcular_crescimento"] is mm.calcular_crescimento
    assert mm.FORMULAS["calcular_valor_faltante"] is mm.calcular_valor_faltante
    assert (
        mm.FORMULAS["calcular_necessidade_diaria"]
        is mm.calcular_necessidade_diaria
    )
    assert mm.FORMULAS["calcular_participacao"] is mm.calcular_participacao


def test_calcular_atingimento_meta_com_valor_vazio_devolve_none():
    """No cruzamento de indicadores um dos lados pode faltar."""
    assert mm.calcular_atingimento_meta(None, 100.0) is None
    assert mm.calcular_atingimento_meta(50.0, None) is None
    assert mm.calcular_atingimento_meta(50.0, 0) is None
