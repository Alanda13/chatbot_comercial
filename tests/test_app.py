from app import preparar_tabela, vale_a_pena_mostrar_tabela

_DADOS_FILIAL_2_ANOS = [
    {"filial": "FERRONORTE LOURIVAL", "ano": 2024, "faturamento": 74414711.88},
    {"filial": "FERRONORTE LOURIVAL", "ano": 2025, "faturamento": 73092760.87},
    {"filial": "FERRONORTE TIBIRI", "ano": 2024, "faturamento": 77799823.48},
    {"filial": "FERRONORTE TIBIRI", "ano": 2025, "faturamento": 87547143.10},
]


def test_tabela_filial_x_2_anos_consultar_dados_comerciais():
    """
    Regressão: uma consulta de "consultar_dados_comerciais" agrupada por
    filial e ano (2 anos) não pode quebrar a resposta inteira — antes de
    "consultar_dados_comerciais" ter uma entrada em
    CONFIG_TABELA_POR_FERRAMENTA, isso levantava KeyError(None) dentro de
    preparar_tabela, e o texto certo da IA era substituído por "None" na
    tela (o erro era capturado e sua mensagem virava a resposta exibida).
    """
    tabela = preparar_tabela(
        _DADOS_FILIAL_2_ANOS,
        "faturamento das filiais",
        "consultar_dados_comerciais",
    )

    assert list(tabela["Filial"]) == [
        "FERRONORTE LOURIVAL",
        "FERRONORTE TIBIRI",
    ]
    assert vale_a_pena_mostrar_tabela(
        _DADOS_FILIAL_2_ANOS, "faturamento das filiais", "consultar_dados_comerciais"
    )


def test_tabela_filial_x_2_anos_ferramenta_sem_config_nao_quebra():
    """
    Qualquer ferramenta futura sem entrada em CONFIG_TABELA_POR_FERRAMENTA
    não deve derrubar a resposta — preparar_tabela cai pro formato padrão
    (linhas de identificação, sem métrica) em vez de lançar KeyError(None).
    """
    tabela = preparar_tabela(
        _DADOS_FILIAL_2_ANOS,
        "faturamento das filiais",
        "ferramenta_que_nao_existe_ainda",
    )

    # Sem config de métrica pra essa ferramenta, cai pro formato longo
    # (uma linha por filial/ano, sem coluna de valor) — não quebra.
    assert "Filial" in tabela.columns
    assert len(tabela) == 4
