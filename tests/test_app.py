from ui.formatacao import descrever_periodo, preparar_tabela, vale_a_pena_mostrar_tabela

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


def test_tabela_de_evolucao_mostra_anterior_diferenca_e_variacao():
    """
    Consultas com "comparar_com" ganham colunas de comparação do campo
    principal do indicador, geradas a partir do catálogo.
    """
    dados = [
        {
            "filial": "FERRONORTE IMPERATRIZ", "nps": 84.83,
            "nps_anterior": 68.56, "diferenca_nps": 16.27,
            "percentual_nps": 23.73,
        },
        {
            "filial": "FERRONORTE TIMON", "nps": 96.28,
            "nps_anterior": 90.11, "diferenca_nps": 6.17,
            "percentual_nps": 6.85,
        },
    ]

    tabela = preparar_tabela(
        dados, "maior evolução de NPS", "consultar_dados_comerciais"
    )

    assert list(tabela.columns) == [
        "Filial", "NPS", "NPS (anterior)", "Diferença NPS", "Variação NPS",
    ]
    assert tabela.iloc[0]["Variação NPS"] == "+23,73%"


def _nps_mensal(filiais, meses):
    dados = []
    for filial in filiais:
        for mes in meses:
            dados.append(
                {
                    "filial": filial, "mes": mes, "nps": 90.5 + mes,
                    "total_respostas": 100 + mes,
                    "percentual_mes_anterior": None if mes == meses[0] else 1.5,
                }
            )
    return dados


def test_duas_filiais_mes_a_mes_viram_colunas_por_filial_com_a_variacao_ao_lado():
    """A dimensão com menos valores (filial) vira colunas; o mês fica nas linhas."""
    tabela = preparar_tabela(
        _nps_mensal(["LOURIVAL", "TIMON"], [1, 2, 3]),
        "comparação do NPS", "consultar_dados_comerciais",
    )

    # o NPS das duas filiais lado a lado, depois a variação de cada uma
    assert list(tabela.columns) == [
        "Mês", "LOURIVAL", "TIMON",
        "LOURIVAL — Variação (mês anterior)", "TIMON — Variação (mês anterior)",
    ]
    assert list(tabela["Mês"]) == ["Janeiro", "Fevereiro", "Março"]
    assert list(tabela["TIMON"]) == ["91,50", "92,50", "93,50"]
    assert tabela.iloc[0]["TIMON — Variação (mês anterior)"] == "sem dados"
    assert tabela.iloc[1]["TIMON — Variação (mês anterior)"] == "+1,50%"


def test_filial_por_ano_vira_colunas_por_ano_e_o_primeiro_ano_nao_tem_variacao():
    dados = [
        {"filial": "TIMON", "ano": 2024, "faturamento": 100.0, "percentual_ano_anterior": None},
        {"filial": "TIMON", "ano": 2025, "faturamento": 150.0, "percentual_ano_anterior": 50.0},
        {"filial": "PICOS", "ano": 2024, "faturamento": 80.0, "percentual_ano_anterior": None},
        {"filial": "PICOS", "ano": 2025, "faturamento": 72.0, "percentual_ano_anterior": -10.0},
    ]

    tabela = preparar_tabela(dados, "faturamento", "consultar_dados_comerciais")

    assert list(tabela.columns) == [
        "Filial", "2024", "2025", "2025 — Variação (ano anterior)",
    ]
    assert tabela.iloc[0]["2025 — Variação (ano anterior)"] == "+50,00%"


def test_pivo_que_passaria_do_limite_de_colunas_continua_comprido():
    """18 filiais x 12 meses: a menor dimensão (12 meses) cabe, mas com
    2 métricas passaria de 12 colunas — não pivota."""
    dados = _nps_mensal([f"FILIAL {i}" for i in range(18)], list(range(1, 13)))

    tabela = preparar_tabela(dados, "NPS e respostas", "consultar_dados_comerciais")

    assert "Filial" in tabela.columns and "Mês" in tabela.columns
    assert len(tabela) == 18 * 12


def test_uma_filial_so_mes_a_mes_continua_com_uma_linha_por_mes():
    """Só há uma dimensão que varia (o mês): nada a pivotar."""
    tabela = preparar_tabela(
        _nps_mensal(["TIMON"], [1, 2, 3]), "NPS", "consultar_dados_comerciais"
    )

    assert len(tabela) == 3
    assert list(tabela["Mês"]) == ["Janeiro", "Fevereiro", "Março"]


def test_colunas_pedidas_limitam_a_tabela_ao_que_foi_pedido():
    """Sem isso a tabela trazia Meta, Faturamento e Respostas que ninguém pediu."""
    dados = [
        {
            "filial": "TIMON", "nps": 96.28, "total_respostas": 5049,
            "percentual_atingimento": 114.99, "valor_meta": 97.5,
            "_colunas_pedidas": ["nps", "percentual_atingimento"],
        },
        {
            "filial": "PICOS", "nps": 97.86, "total_respostas": 4113,
            "percentual_atingimento": 93.62, "valor_meta": 50.4,
            "_colunas_pedidas": ["nps", "percentual_atingimento"],
        },
    ]

    tabela = preparar_tabela(dados, "NPS e atingimento", "consultar_dados_comerciais")

    assert list(tabela.columns) == ["Filial", "NPS", "Atingimento"]
    assert list(tabela["NPS"]) == ["96,28", "97,86"]
    assert list(tabela["Atingimento"]) == ["114,99%", "93,62%"]


def test_colunas_pedidas_trazem_a_comparacao_do_campo_pedido():
    dados = [
        {
            "filial": "TIMON", "nps": 95.78, "nps_anterior": 83.07,
            "diferenca_nps": 12.71, "percentual_nps": 15.3, "total_respostas": 2960,
            "_colunas_pedidas": ["nps"],
        },
        {
            "filial": "LOURIVAL", "nps": 75.24, "nps_anterior": 66.41,
            "diferenca_nps": 8.83, "percentual_nps": 13.3, "total_respostas": 832,
            "_colunas_pedidas": ["nps"],
        },
    ]

    tabela = preparar_tabela(dados, "NPS do semestre", "consultar_dados_comerciais")

    assert list(tabela.columns) == [
        "Filial", "NPS", "NPS (anterior)", "Diferença NPS", "Variação NPS",
    ]


def test_numeros_saem_em_portugues_e_contagens_sem_casa_decimal():
    """Antes saíam "96.28" e "1058.0" (a coluna virava decimal por causa
    de uma filial sem dado)."""
    dados = [
        {"filial": "TIMON", "nps": 96.28, "total_respostas": 1058.0},
        {"filial": "MARITUBA", "nps": None, "total_respostas": None},
    ]

    tabela = preparar_tabela(dados, "NPS e respostas", "consultar_dados_comerciais")

    assert list(tabela["NPS"]) == ["96,28", "sem dados"]
    assert list(tabela["Respostas"]) == ["1.058", "sem dados"]


def test_nps_das_filiais_comparadas_fica_lado_a_lado_antes_das_outras_colunas():
    """Regressão: com Respostas e Variação junto, o NPS de uma filial ficava
    separado do NPS da outra por essas colunas, e a comparação se perdia."""
    dados = _nps_mensal(["LOURIVAL", "SANTA INÊS"], [1, 2, 3])

    tabela = preparar_tabela(
        dados, "NPS com base em 100 respostas", "consultar_dados_comerciais"
    )

    assert list(tabela.columns)[:5] == [
        "Mês", "LOURIVAL — NPS", "SANTA INÊS — NPS",
        "LOURIVAL — Respostas", "SANTA INÊS — Respostas",
    ]


def test_tabela_esparsa_nao_vira_colunas():
    """
    5 pares RCA x cliente, cada cliente de um RCA só: virar os RCAs em
    colunas deixava quase todas as células "sem dados" — fica em linhas.
    """
    dados = [
        {"rca": 1, "rca_nome": "VITOR", "cliente": 10, "cliente_nome": "A", "valor_desconto": 30.0},
        {"rca": 2, "rca_nome": "PAULO", "cliente": 11, "cliente_nome": "B", "valor_desconto": 21.0},
        {"rca": 2, "rca_nome": "PAULO", "cliente": 12, "cliente_nome": "C", "valor_desconto": 20.0},
        {"rca": 2, "rca_nome": "PAULO", "cliente": 13, "cliente_nome": "D", "valor_desconto": 19.0},
        {"rca": 3, "rca_nome": "EDMILSON", "cliente": 14, "cliente_nome": "E", "valor_desconto": 13.0},
    ]

    tabela = preparar_tabela(dados, "desconto por rca e cliente", "consultar_dados_comerciais")

    assert len(tabela) == 5
    assert list(tabela["RCA"]) == ["VITOR", "PAULO", "PAULO", "PAULO", "EDMILSON"]


def test_legenda_nao_confunde_codigo_com_ano():
    """'(código 1901)' e '(código 2360)' são códigos de RCA, não anos."""
    texto = (
        "Os RCAs que mais faturaram de 28/09/2026 a 04/10/2026: AURORA "
        "ANDRADE-F01 (código 1901) e LUANA SOUSA ALMEIDA - F27 (código 2360)."
    )

    assert descrever_periodo([{"rca": 1901, "faturamento": 1.0}], texto) == "Ano: 2026"


def test_percentual_muito_pequeno_nao_aparece_como_zero():
    from ui.formatacao import formatar_percentual_atingimento

    assert formatar_percentual_atingimento(0.0034) == "menos de 0,01%"
    assert formatar_percentual_atingimento(0.0) == "0,00%"
    assert formatar_percentual_atingimento(3.1307) == "3,13%"


def test_diferenca_em_reais_mostra_o_sinal():
    from ui.formatacao import formatar_moeda_com_sinal

    assert formatar_moeda_com_sinal(14287298.37) == "+R$ 14.287.298,37"
    assert formatar_moeda_com_sinal(-963253.53) == "−R$ 963.253,53"


def test_texto_da_conversa_tem_perguntas_respostas_e_tabela():
    from datetime import datetime

    from ui.components.exportar_conversa import montar_texto_da_conversa

    dados = [
        {"filial": "TIMON", "faturamento": 100.0, "_colunas_pedidas": ["faturamento"]},
        {"filial": "IMPERATRIZ", "faturamento": 80.0, "_colunas_pedidas": ["faturamento"]},
    ]
    texto = montar_texto_da_conversa(
        [
            {"papel": "user", "conteudo": "faturamento por filial"},
            {"papel": "assistant", "conteudo": "**Faturamento** por filial:",
             "dados_tabela": dados, "nome_ferramenta": "consultar_dados_comerciais"},
        ],
        datetime(2026, 10, 8, 11, 40),
    )

    assert "conversa de 08/10/2026 às 11:40" in texto
    assert "Você: faturamento por filial" in texto
    assert "Chatbot: Faturamento por filial:" in texto   # sem os **
    assert "R$ 100,00" in texto and "IMPERATRIZ" in texto


def test_tabela_com_primeira_coluna_repetida_nao_quebra():
    """'Os 5 RCAs de cada mês': "Janeiro" repete na 1ª coluna — o alinhamento
    célula a célula do Styler quebrava com índice repetido."""
    from ui.components.tabela import exibir_tabela

    dados = [
        {"mes": mes, "rca": rca, "rca_nome": nome, "faturamento": valor, "ano": 2026,
         "_colunas_pedidas": ["faturamento"]}
        for mes, rca, nome, valor in [
            (1, 10, "ANA", 300.0), (1, 11, "BRUNO", 200.0),
            (2, 10, "ANA", 250.0), (2, 12, "CARLA", 240.0),
            (3, 10, "ANA", 260.0), (3, 13, "DIEGO", 230.0),
            (4, 10, "ANA", 270.0), (4, 14, "ELISA", 220.0),
        ]
    ]
    from ui.formatacao import preparar_tabela
    assert preparar_tabela(dados, "faturamento", "consultar_dados_comerciais").iloc[:, 0].duplicated().any()

    exibir_tabela(dados, "faturamento", chave="teste", nome_ferramenta="consultar_dados_comerciais")
