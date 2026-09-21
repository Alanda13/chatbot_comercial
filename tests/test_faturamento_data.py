from src import faturamento_data as fd


def test_carregar_faturamento_8280_padroniza_filiais(monkeypatch, tmp_path):
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
    monkeypatch.setattr(fd, "ARQUIVO_8280", arquivo)

    dados = fd.carregar_faturamento_8280()

    assert list(dados["FILIAL"]) == ["TIMON", "ARAGUAÍNA", "ARAGUAÍNA"]
    assert list(dados["CODFILIAL"]) == [9, 24, 24]
    assert list(dados["ESTADO"]) == ["MA", "TO", "TO"]
