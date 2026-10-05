from src import faturamento_data as fd


def test_carregar_faturamento_mensal_padroniza_filiais(monkeypatch, tmp_path):
    """
    Só as lojas da planilha ficam, com o nome padrão e o estado; o código
    30 (ARAGUAINAV) é somado ao 24 (ARAGUAÍNA).
    """
    arquivo = tmp_path / "faturamento.csv"
    arquivo.write_text(
        "CODFILIAL;FILIAL;COD_RCA;VENDA_LIQ\n"
        "9;FERRONORTE TIMON;1901;10,5\n"
        "24;FERRONORTE ARAGUAINA;1902;20,0\n"
        "30;FERRONORTE ARAGUAINAV;1903;5,0\n"
        "22;FN ATACADO;1904;999,0\n",
        encoding="latin1",
    )
    monkeypatch.setattr(fd, "ARQUIVO_FATURAMENTO_MENSAL", arquivo)

    dados = fd.carregar_faturamento_mensal()

    assert list(dados["FILIAL"]) == ["TIMON", "ARAGUAÍNA", "ARAGUAÍNA"]
    assert list(dados["CODFILIAL"]) == [9, 24, 24]
    assert list(dados["ESTADO"]) == ["MA", "TO", "TO"]


def test_gerar_tabela_mantem_meta_sem_venda_e_marca_conta_da_empresa(monkeypatch):
    """
    Igual à rotina 8139: a meta de quem não vendeu no mês entra (ex: a
    conta "COMERCIAL FERRONORTE LTDA-F09-TIMON"), com venda zero e o
    supervisor do cadastro — antes ela sumia e a meta da filial ficava
    menor que a do banco.
    """
    import pandas as pd

    chave = {"CODFILIAL": "9", "ANO": 2026, "MES": 9}
    vendas = pd.DataFrame([{**chave, "CODUSUR": 8857, "CODSUPERVISOR": 9, "NOME_SUPERVISOR": "SUP TIMON",
                            "QT_NOTAS": 10, "VENDA_BRUTA": 2000.0, "VENDA_TABELA": 2100.0, "VALORDESC": 50.0}])
    meta = pd.DataFrame([{**chave, "CODUSUR": 8857, "VALOR_META": 3000.0},
                         {**chave, "CODUSUR": 8468, "VALOR_META": 466.0},
                         {**chave, "CODUSUR": 7777, "VALOR_META": 0.0}])
    cadastro = pd.DataFrame([
        {"CODUSUR": 8857, "NOME_RCA": "DIMY ALYSSON - F09", "COD_SUPERVISOR_CAD": 9, "NOME_SUPERVISOR_CAD": "SUP TIMON"},
        {"CODUSUR": 8468, "NOME_RCA": "COMERCIAL FERRONORTE LTDA-F09-TIMON", "COD_SUPERVISOR_CAD": 9,
         "NOME_SUPERVISOR_CAD": "SUP TIMON"},
    ])
    vazio = pd.DataFrame(columns=[*chave, "CODUSUR"])

    class Conexao:
        def cursor(self): return None
        def close(self): pass

    monkeypatch.setattr(fd, "get_connection", Conexao)
    monkeypatch.setattr(fd, "_consultar_vendas", lambda cursor, desde: vendas)
    monkeypatch.setattr(fd, "_consultar_peso", lambda cursor, desde: vazio.assign(PESOLIQ=[]))
    monkeypatch.setattr(fd, "_consultar_devolucao", lambda cursor, desde: vazio.assign(VALOR_DEV=[]))
    monkeypatch.setattr(fd, "_consultar_meta", lambda cursor, desde: meta)
    monkeypatch.setattr(fd, "_consultar_cadastro_rca", lambda cursor: cadastro)

    tabela = fd.gerar_tabela(2026).set_index("COD_RCA")

    assert tabela["VALOR_META"].sum() == 3466.0          # meta igual à 8139
    assert 7777 not in tabela.index                        # meta zero e sem venda: fora
    assert tabela.loc[8468, "VENDA_LIQ"] == 0.0
    assert tabela.loc[8468, "COD_SUPERVISOR"] == 9
    assert bool(tabela.loc[8468, "CONTA_EMPRESA"]) is True
    assert bool(tabela.loc[8857, "CONTA_EMPRESA"]) is False
