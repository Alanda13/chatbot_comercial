from src.conferencia_numeros import numeros_inventados, valores_permitidos

_RESULTADO = {
    "periodo_consultado": {"descricao": "de 01/01/2026 a 06/10/2026"},
    "resultados": [
        {"filial": "PICOS", "nps": 99.1, "percentual_desconto": 1.2067, "valor_desconto": 479904.09},
        {"filial": "PARNAIBA", "nps": 91.61, "percentual_desconto": 6.5931, "valor_desconto": 2038298.06},
    ],
}
_SAIDA_DO_CODIGO = (
    "Acima de 90: %somas=3.14%, total=R$ 8,566,753.98\n"
    "Correlação: 0.26\nSem Parnaíba: 2.70%"
)


def _permitidos():
    return valores_permitidos(_RESULTADO, "as filiais com nps acima de 90?",
                              saidas_de_codigo=[_SAIDA_DO_CODIGO])


def test_arredondamentos_e_abreviacoes_dos_dados_passam():
    texto = (
        "De 01/01/2026 a 06/10/2026, as 7 filiais com NPS acima de 90 dão 3,14% "
        "(R$ 8,57 mi; R$ 8.566.753,98). Picos tem NPS 99,1 e 1,21%; Parnaíba "
        "6,59%. Sem Parnaíba, 2,70%. Relação fraca (0,26)."
    )

    assert numeros_inventados(texto, _permitidos()) == []


def test_numero_diferente_do_codigo_e_pego():
    """O código imprimiu 2,70%; o texto saiu com 2,75% (caso real)."""
    texto = "Sem Parnaíba, o grupo cai para 2,75%."

    assert numeros_inventados(texto, _permitidos()) == ["2,75"]


def test_valor_em_reais_inventado_e_pego():
    texto = "O grupo deu R$ 9.100.000,00 de desconto."

    assert numeros_inventados(texto, _permitidos()) == ["9.100.000,00"]
