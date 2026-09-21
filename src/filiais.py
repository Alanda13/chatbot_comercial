"""
Lojas atendidas pelo chatbot (planilha Filiais.xlsx) — a ÚNICA lista de
filiais do projeto.

Só essas lojas existem pro chatbot: todo carregador de dados passa o
DataFrame por `padronizar_filiais`, que descarta as outras e troca o
nome da filial pelo nome da planilha. Assim as quatro bases (faturamento,
meta, meta de tonelada e NPS), que escrevem o nome de formas diferentes,
passam a usar o mesmo nome e o mesmo código — o que permite cruzar
indicadores por filial sem comparar nomes.
"""
import re

import pandas as pd

from src.filial_utils import encontrar_filial_mais_proxima, normalizar_nome_filial

# código da filial (CODFILIAL do Winthor) -> (nome, estado)
LOJAS = {
    1: ("CAMPOS SALES", "PI"),
    2: ("LOURIVAL", "PI"),
    4: ("SANTA INÊS", "MA"),
    5: ("GUAJAJARAS", "MA"),
    6: ("AREINHA", "MA"),
    7: ("TIBIRI", "MA"),
    8: ("JOÃO XXIII", "PI"),
    9: ("TIMON", "MA"),
    10: ("METALURGICA", "PI"),
    11: ("IMPERATRIZ", "MA"),
    12: ("PARNAIBA", "PI"),
    14: ("PICOS", "PI"),
    18: ("INOX E ALUMINIO", "PI"),
    24: ("ARAGUAÍNA", "TO"),
    27: ("VIT.CONQUISTA", "BA"),
    28: ("ARACAGY", "MA"),
    31: ("MARITUBA", "PA"),
    32: ("MAIOBÃO", "MA"),
}

# Códigos que a planilha soma dentro de outra loja: o 30 (ARAGUAINAV)
# entra em ARAGUAÍNA (24).
CODIGO_UNIFICADO = {30: 24}

CODIGO_POR_NOME = {nome: codigo for codigo, (nome, _) in LOJAS.items()}

_ESTADOS = {
    "pi": "PI", "piaui": "PI", "ma": "MA", "maranhao": "MA",
    "to": "TO", "tocantins": "TO", "ba": "BA", "bahia": "BA",
    "pa": "PA", "para": "PA",
}


def padronizar_filiais(dados: pd.DataFrame, codigos: pd.Series) -> pd.DataFrame:
    """
    Recebe os dados de uma base e o código de filial de cada linha
    (`codigos`, alinhado ao índice de `dados`). Devolve só as linhas das
    lojas da planilha, com FILIAL (nome padrão), CODFILIAL (já com o 30
    somado ao 24) e ESTADO preenchidos.
    """
    codigos = codigos.replace(CODIGO_UNIFICADO)
    dados = dados[codigos.isin(LOJAS)].copy()
    codigos = codigos[dados.index]

    dados["CODFILIAL"] = codigos
    dados["FILIAL"] = codigos.map(lambda codigo: LOJAS[codigo][0])
    dados["ESTADO"] = codigos.map(lambda codigo: LOJAS[codigo][1])

    return dados.reset_index(drop=True)


def descrever_codigos_somados() -> str:
    """Frase pro prompt: quais códigos estão somados a qual loja."""
    return "; ".join(
        f"o código {codigo} está somado à filial {LOJAS[destino][0]} "
        f"(código {destino}) — escreva '{LOJAS[destino][0]} (códigos "
        f"{destino} e {codigo} somados)'"
        for codigo, destino in CODIGO_UNIFICADO.items()
    )


def listar_filiais() -> list[str]:
    return sorted(nome for nome, _ in LOJAS.values())


def resolver_nome_filial(nome_informado: str) -> str:
    """
    Encontra o nome padrão da filial a partir do que foi digitado —
    o nome (tolerando variações de escrita e pequenos erros) ou o código
    ("30", "filial 30", "codfilial 30"). O código 30 resolve pra
    ARAGUAÍNA, onde ele está somado.
    """
    normalizado = normalizar_nome_filial(str(nome_informado))
    codigo = re.fullmatch(r"(?:cod\w*\s*)?0*(\d+)", normalizado)

    if codigo:
        numero = int(codigo.group(1))
        numero = CODIGO_UNIFICADO.get(numero, numero)

        if numero not in LOJAS:
            raise ValueError(
                f"O código de filial {codigo.group(1)} não foi encontrado."
            )

        return LOJAS[numero][0]

    encontrada = encontrar_filial_mais_proxima(normalizado, listar_filiais())

    if encontrada is None:
        raise ValueError(f"A filial '{nome_informado}' não foi encontrada.")

    return encontrada


def resolver_estado(valor: str) -> str:
    """Aceita a sigla ou o nome do estado (ex: "MA", "Maranhão")."""
    sigla = _ESTADOS.get(normalizar_nome_filial(str(valor)))

    if sigla is None:
        raise ValueError(f"O estado '{valor}' não foi encontrado.")

    return sigla
