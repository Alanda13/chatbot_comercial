"""
Situação dos clientes (ativo, em risco, inativo, novo, recuperado).

Contada em dias, pelas compras do cliente em QUALQUER filial:
- ativo: comprou há menos de 90 dias (os 90 dias do WinThor:
  PCCONSUM.NUMDIASCLIINATIV);
- em risco de perda: de 60 a 89 dias sem comprar (continua ativo);
- inativo: de 90 dias a 1 ano sem comprar;
- parado há mais de 1 ano: contado à parte;
- novo: a 1ª compra (desde 2020) foi naquele mês;
- recuperado: no mês, voltou a comprar depois de 90 dias ou mais parado
  (DIAS_PARADO_ANTES_DE_VOLTAR guarda quanto tempo ficou parado, de
  qualquer tamanho);
- frequência de compra: em média, a cada quantos dias o cliente comprou nos
  12 meses até a data da foto (compras no mesmo dia = 1; com 1 compra só,
  fica vazia).

Da última compra: data e filial; valor (venda bruta), nota(s), pedido(s) e
RCA vêm do arquivo de notas (`venda_repository`), que começa em 2025 — antes
disso, vazios. Várias notas no mesmo dia são uma compra só: o valor soma.

"Cliente de Timon" / "do RCA 8952" = comprou em Timon (com o RCA) nos 12
meses antes da SUA última compra — o cadastro (PCCLIENT) não tem a filial
preenchida. Quem está ativo só por compras em OUTRA filial (ou com outro
RCA) é marcado, pra resposta avisar.

Um CSV, gerado do Oracle e atualizado em segundo plano por
`core/services/atualizador_service.py`: `compras_clientes.csv` — os dias
em que cada cliente comprou, por filial/RCA, desde 2020. A "foto" de um
mês (a situação no último dia; no mês atual, hoje) é montada na memória
só quando uma pergunta pede aquele mês.
"""
import calendar
from collections import OrderedDict
from datetime import date

import pandas as pd

from core.repositories.arquivos_repository import (
    garantir,
    gravar_csv,
    inicio_da_janela_parcial,
    ler_csv,
)
from core.repositories import cliente_repository, venda_repository
from core.repositories.faturamento_repository import RAIZ_PROJETO, _FILTRO_VENDA_VALIDA
from core.repositories.filiais_repository import CODIGO_UNIFICADO, LOJAS, padronizar_filiais
from core.logger import obter_logger

logger = obter_logger(__name__)

ARQUIVO_COMPRAS_CLIENTES = RAIZ_PROJETO / "data" / "compras_clientes.csv"
INICIO_COMPRAS = date(2020, 1, 1)
# 2020 não tem histórico pra contar dias sem comprar: a foto começa em 2021.
ANO_INICIO_SITUACAO = 2021

DIAS_INATIVO = 90
DIAS_EM_RISCO = 60
DIAS_PARADO_HA_MAIS_DE_1_ANO = 365
DIAS_CLIENTE_DA_FILIAL = 365
DIAS_JANELA_FREQUENCIA = 365

COLUNAS_COMPRAS = ["CODCLI", "CODFILIAL", "COD_RCA", "COD_SUPERVISOR", "DATA"]


def _buscar(desde: date) -> pd.DataFrame:
    from core.repositories.oracle import get_connection

    conexao = get_connection()

    try:
        cursor = conexao.cursor()
        cursor.arraysize = 20000
        cursor.execute(
            f"""
            SELECT V.CODCLI, V.CODFILIAL, V.CODUSUR COD_RCA,
                   V.CODSUPERVISOR COD_SUPERVISOR, TRUNC(V.DTSAIDA) DATA
            FROM VIEW_VENDAS_RESUMO_FATURAMENTO V
            WHERE V.DTSAIDA >= :desde
            {_FILTRO_VENDA_VALIDA}
            GROUP BY V.CODCLI, V.CODFILIAL, V.CODUSUR, V.CODSUPERVISOR, TRUNC(V.DTSAIDA)
            HAVING SUM(V.VLVENDA) > 0
            """,
            desde=desde,
        )
        dados = pd.DataFrame(cursor.fetchall(), columns=[d[0] for d in cursor.description])
    finally:
        conexao.close()

    dados["DATA"] = pd.to_datetime(dados["DATA"])

    for coluna in ("CODCLI", "CODFILIAL", "COD_RCA"):
        dados[coluna] = dados[coluna].astype("int64")

    return dados[COLUNAS_COMPRAS]


def atualizar(completa: bool) -> None:
    """Completa: tudo desde 2020. Parcial: só o mês atual e o anterior,
    juntando com os dias mais antigos do CSV."""
    if completa or not ARQUIVO_COMPRAS_CLIENTES.exists():
        dados = _buscar(INICIO_COMPRAS)
    else:
        desde = inicio_da_janela_parcial()
        antigo = _ler_compras()
        antigo = antigo[antigo["DATA"] < pd.Timestamp(desde)]
        dados = pd.concat([antigo, _buscar(desde)], ignore_index=True)

    gravar_csv(dados, ARQUIVO_COMPRAS_CLIENTES)


def _garantir() -> None:
    garantir([ARQUIVO_COMPRAS_CLIENTES], atualizar, "compras dos clientes")


def _ler_compras() -> pd.DataFrame:
    dados = ler_csv(ARQUIVO_COMPRAS_CLIENTES)
    dados["DATA"] = pd.to_datetime(dados["DATA"], format="ISO8601")
    return dados


def _numero_do_mes(datas: pd.Series) -> pd.Series:
    return datas.dt.year * 12 + datas.dt.month - 1


def _primeiro_mes(compras: pd.DataFrame) -> pd.Series:
    """Mês da 1ª compra de cada cliente desde 2020 (ano*12 + mês-1)."""
    return _numero_do_mes(compras.groupby("CODCLI")["DATA"].min())


def _meses_recuperados(compras: pd.DataFrame) -> pd.DataFrame:
    """(CODCLI, mês) em que o cliente voltou a comprar, com o maior tempo
    que ele ficou parado antes de uma compra daquele mês
    (DIAS_PARADO_ANTES_DE_VOLTAR, de qualquer tamanho: "voltou depois de 2
    meses parado" também responde). Recuperado = 90 dias ou mais."""
    dias = compras[["CODCLI", "DATA"]].drop_duplicates().sort_values(["CODCLI", "DATA"])
    parado = (dias["DATA"] - dias.groupby("CODCLI")["DATA"].shift()).dt.days
    voltas = pd.DataFrame({
        "CODCLI": dias["CODCLI"],
        "MES_NUMERO": _numero_do_mes(dias["DATA"]),
        "DIAS_PARADO_ANTES_DE_VOLTAR": parado,
    }).dropna()
    return (
        voltas.groupby(["CODCLI", "MES_NUMERO"], as_index=False)["DIAS_PARADO_ANTES_DE_VOLTAR"]
        .max()
        .astype({"DIAS_PARADO_ANTES_DE_VOLTAR": "int64"})
    )


def _frequencia_de_compra(ate: pd.DataFrame, referencia: pd.Timestamp) -> pd.Series:
    """Por cliente: (última − primeira compra) ÷ (nº de dias com compra − 1),
    nas compras dos últimos 12 meses — a média dos intervalos."""
    janela = ate.loc[
        ate["DATA"] > referencia - pd.Timedelta(days=DIAS_JANELA_FREQUENCIA), ["CODCLI", "DATA"]
    ].drop_duplicates()
    compras = janela.groupby("CODCLI")["DATA"].agg(["min", "max", "count"])
    intervalo = (compras["max"] - compras["min"]).dt.days / (compras["count"] - 1)
    return intervalo.where(compras["count"] > 1).round(1)


def _foto_do_mes(
    compras: pd.DataFrame, referencia: pd.Timestamp, primeiro_mes: pd.Series,
    recuperados: pd.DataFrame,
) -> pd.DataFrame:
    ate = compras[compras["DATA"] <= referencia].sort_values("DATA")
    mes_numero = referencia.year * 12 + referencia.month - 1

    ultima = ate.drop_duplicates("CODCLI", keep="last")[
        ["CODCLI", "DATA", "CODFILIAL", "COD_RCA"]
    ].rename(columns={
        "DATA": "DATA_ULTIMA_COMPRA",
        "CODFILIAL": "FILIAL_ULTIMA_COMPRA",
        "COD_RCA": "RCA_ULTIMA_COMPRA",
    })

    # Cliente de cada filial/RCA: quem comprou ali nos 12 meses antes da
    # última compra dele (ver o começo do arquivo).
    ultima_do_cliente = ate["CODCLI"].map(ultima.set_index("CODCLI")["DATA_ULTIMA_COMPRA"])
    janela = ate[ate["DATA"] > ultima_do_cliente - pd.Timedelta(days=DIAS_CLIENTE_DA_FILIAL)]
    foto = janela.drop_duplicates(["CODCLI", "CODFILIAL", "COD_RCA"], keep="last").rename(
        columns={"DATA": "ULTIMA_COM_RCA"}
    )
    na_filial = janela.groupby(["CODCLI", "CODFILIAL"])["DATA"].max().rename("ULTIMA_NA_FILIAL")
    foto = foto.join(na_filial, on=["CODCLI", "CODFILIAL"]).merge(ultima, on="CODCLI")

    dias = (referencia - foto["DATA_ULTIMA_COMPRA"]).dt.days
    ativo = dias < DIAS_INATIVO
    parado_ha_mais_de_1_ano = dias >= DIAS_PARADO_HA_MAIS_DE_1_ANO

    foto["ANO"] = referencia.year
    foto["MES"] = referencia.month
    foto["DIAS_SEM_COMPRAR"] = dias
    foto["ATIVO"] = ativo
    foto["EM_RISCO"] = ativo & (dias >= DIAS_EM_RISCO)
    foto["INATIVO"] = ~ativo & ~parado_ha_mais_de_1_ano
    foto["PARADO_HA_MAIS_DE_1_ANO"] = parado_ha_mais_de_1_ano
    foto["NOVO"] = foto["CODCLI"].map(primeiro_mes) == mes_numero
    # Sem compra no mês (ou 1ª compra): 0.
    foto["DIAS_PARADO_ANTES_DE_VOLTAR"] = foto["CODCLI"].map(
        recuperados.loc[recuperados["MES_NUMERO"] == mes_numero]
        .set_index("CODCLI")["DIAS_PARADO_ANTES_DE_VOLTAR"]
    ).fillna(0).astype("int64")
    foto["RECUPERADO"] = foto["DIAS_PARADO_ANTES_DE_VOLTAR"] >= DIAS_INATIVO
    foto["FREQUENCIA_DE_COMPRA"] = foto["CODCLI"].map(_frequencia_de_compra(ate, referencia))
    # Ativo só por compra em outra filial / com outro RCA: a resposta avisa.
    foto["SO_OUTRA_FILIAL"] = ativo & (
        (referencia - foto["ULTIMA_NA_FILIAL"]).dt.days >= DIAS_INATIVO
    )
    foto["SO_OUTRO_RCA"] = ativo & (
        (referencia - foto["ULTIMA_COM_RCA"]).dt.days >= DIAS_INATIVO
    )
    return foto.drop(columns=["ULTIMA_COM_RCA", "ULTIMA_NA_FILIAL"])


_MARCAS = [
    "ATIVO", "EM_RISCO", "INATIVO", "PARADO_HA_MAIS_DE_1_ANO", "NOVO", "RECUPERADO",
    "SO_OUTRA_FILIAL", "SO_OUTRO_RCA",
]
COLUNAS_SITUACAO = [
    "ANO", "MES", "CODCLI", "CODFILIAL", "COD_RCA", "COD_SUPERVISOR", *_MARCAS,
    "DIAS_SEM_COMPRAR", "DIAS_PARADO_ANTES_DE_VOLTAR", "FREQUENCIA_DE_COMPRA", "DATA_ULTIMA_COMPRA", "FILIAL_ULTIMA_COMPRA", "RCA_ULTIMA_COMPRA",
]


def _referencia(ano: int, mes: int, hoje: date) -> pd.Timestamp:
    """O último dia do mês; no mês atual, hoje."""
    return pd.Timestamp(min(date(ano, mes, calendar.monthrange(ano, mes)[1]), hoje))


def meses_validos(meses: list[tuple[int, int]], hoje: date) -> list[tuple[int, int]]:
    """Só os meses que têm foto: de 2021 até o atual."""
    return sorted({
        (ano, mes) for ano, mes in meses
        if (ANO_INICIO_SITUACAO, 1) <= (ano, mes) <= (hoje.year, hoje.month)
    })


def montar_situacao(
    compras: pd.DataFrame, meses: list[tuple[int, int]], hoje: date | None = None
) -> pd.DataFrame:
    """A foto de cada mês pedido (ano, mês)."""
    hoje = hoje or date.today()
    primeiro_mes = _primeiro_mes(compras)
    recuperados = _meses_recuperados(compras)
    fotos = [
        _foto_do_mes(compras, _referencia(ano, mes, hoje), primeiro_mes, recuperados)
        for ano, mes in meses_validos(meses, hoje)
    ]

    if not fotos:
        return pd.DataFrame(columns=COLUNAS_SITUACAO)

    situacao = pd.concat(fotos, ignore_index=True)[COLUNAS_SITUACAO]
    situacao[_MARCAS] = situacao[_MARCAS].astype("int8")
    return situacao


def _juntar_textos(valores: pd.Series) -> str:
    """"123", "123 e 456", "123, 456 e 789" — sem repetir."""
    textos = list(dict.fromkeys(str(valor) for valor in valores.dropna()))
    return " e ".join([", ".join(textos[:-1]), textos[-1]]) if len(textos) > 1 else "".join(textos)


def _moeda(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def detalhes_da_ultima_compra(situacao: pd.DataFrame, vendas: pd.DataFrame) -> pd.DataFrame:
    """Valor, nota(s), pedido(s) e RCA(s) das notas do dia da última compra
    de cada cliente (ver o começo do arquivo), em texto."""
    chaves = ["CODCLI", "DATA_ULTIMA_COMPRA"]
    textos = {"NUMNOTA": "NOTA_ULTIMA_COMPRA", "NUMPED": "PEDIDO_ULTIMA_COMPRA", "NOME_RCA": "NOME_RCA_ULTIMA_COMPRA"}
    do_dia = vendas[["CODCLI", "DATA", *textos, "VENDA_BRUTA"]].merge(
        situacao[chaves].drop_duplicates(), left_on=["CODCLI", "DATA"], right_on=chaves
    )
    # Quase todo mundo tem 1 nota no dia: só os outros passam por
    # _juntar_textos (um por um seria lento).
    varias = do_dia.groupby(chaves)["NUMNOTA"].transform("size") > 1
    detalhes = pd.concat([
        do_dia[~varias].set_index(chaves)[list(textos)].astype({"NUMNOTA": str, "NUMPED": str}),
        do_dia[varias].groupby(chaves)[list(textos)].agg(_juntar_textos),
    ]).rename(columns=textos)
    detalhes["VALOR_ULTIMA_COMPRA"] = do_dia.groupby(chaves)["VENDA_BRUTA"].sum().map(_moeda)
    return situacao.join(detalhes, on=chaves)


def _para_consulta(situacao: pd.DataFrame) -> pd.DataFrame:
    """
    A foto pronta pro motor:
    - CLIENTE_ATIVO, CLIENTE_NOVO...: o código do cliente quando ele está
      naquela situação (vazio quando não) — o motor conta os códigos
      DIFERENTES, e o cliente que comprou com 2 RCAs conta 1 vez só;
    - nome/CNPJ/empresa do cadastro, nome da filial;
    - situação, última compra e filial dela em texto, pra listas de clientes.
    Mais recente primeiro: numa lista de clientes, o que vem junto com
    cada um (dias sem comprar, última compra) é da foto mais nova.
    """
    dados = detalhes_da_ultima_compra(
        situacao.sort_values(["ANO", "MES"], ascending=False, kind="stable"),
        venda_repository.carregar_notas_dos_clientes(),
    )

    for marca in _MARCAS:
        dados[f"CLIENTE_{marca}"] = dados["CODCLI"].where(dados[marca] == 1).astype("Int32")

    dados["SITUACAO"] = pd.Categorical.from_codes(
        dados["ATIVO"] + dados["EM_RISCO"] + 3 * dados["PARADO_HA_MAIS_DE_1_ANO"],
        ["Inativo", "Ativo", "Em risco de perda", "Parado há mais de 1 ano"],
    )
    # Formata cada data/filial uma vez só (são poucas, repetidas em muitas
    # linhas).
    datas = dados["DATA_ULTIMA_COMPRA"].astype("category")
    dados["ULTIMA_COMPRA"] = datas.cat.rename_categories(
        datas.cat.categories.strftime("%d/%m/%Y")
    )
    filiais = dados["FILIAL_ULTIMA_COMPRA"].astype("category")
    dados["FILIAL_ULTIMA_COMPRA"] = filiais.cat.rename_categories(
        [LOJAS.get(codigo, (f"código {codigo}",))[0] for codigo in filiais.cat.categories]
    )

    # Texto como categoria: centenas de mil linhas com nome do cliente
    # repetido ocupariam centenas de MB.
    clientes = cliente_repository.carregar_clientes()[
        ["CODCLI", "CLIENTE", "CNPJ", "CIDADE", "EMPRESA", "NOME_EMPRESA", "CNPJ_EMPRESA"]
    ]
    clientes = clientes.astype({coluna: "category" for coluna in clientes.columns if coluna != "CODCLI"})
    dados = dados.merge(clientes, on="CODCLI", how="left")
    dados = padronizar_filiais(dados, dados["CODFILIAL"])
    return dados.astype({
        coluna: "category" for coluna in (
            "FILIAL", "ESTADO", "VALOR_ULTIMA_COMPRA", "NOTA_ULTIMA_COMPRA",
            "PEDIDO_ULTIMA_COMPRA", "NOME_RCA_ULTIMA_COMPRA",
        )
    })


# As compras (e quem voltou a comprar) ficam em memória até o arquivo mudar;
# cada foto pedida também (~1 s pra montar), até o arquivo mudar ou o dia
# virar — no máximo as 24 mais recentes pedidas.
_MAXIMO_DE_FOTOS = 24
_cache: dict = {"versao": None, "compras": None, "fotos": OrderedDict()}


def _meses_dos_filtros(filtros: dict | None, hoje: date) -> list[tuple[int, int]]:
    """Os meses do período da pergunta (filtros "ano"/"mes" já resolvidos
    pelo motor). Sem ano: o mês atual."""
    filtros = filtros or {}
    anos = [int(ano) for ano in filtros.get("ano") or []]
    meses = [int(mes) for mes in filtros.get("mes") or []]

    if not anos:
        return [(hoje.year, mes) for mes in meses] or [(hoje.year, hoje.month)]

    return [(ano, mes) for ano in anos for mes in (meses or range(1, 13))]


def carregar_situacao_clientes(filtros: dict | None = None) -> pd.DataFrame:
    """A foto dos meses do período pedido (ver o começo do arquivo)."""
    _garantir()
    hoje = date.today()
    versao = (ARQUIVO_COMPRAS_CLIENTES.stat().st_mtime, hoje)

    if _cache["versao"] != versao:
        compras = _ler_compras()
        # Os códigos somados numa loja só (ex: 30 → 24) contam como a mesma filial.
        compras["CODFILIAL"] = compras["CODFILIAL"].replace(CODIGO_UNIFICADO)
        _cache.update(versao=versao, compras=compras, fotos=OrderedDict())

    fotos = _cache["fotos"]
    pedidos = meses_validos(_meses_dos_filtros(filtros, hoje), hoje)
    faltando = [mes for mes in pedidos if mes not in fotos]

    if faltando:
        montadas = _para_consulta(montar_situacao(_cache["compras"], faltando, hoje))

        for ano, mes in faltando:
            fotos[(ano, mes)] = montadas[(montadas["ANO"] == ano) & (montadas["MES"] == mes)]

    for mes in pedidos:
        fotos.move_to_end(mes)

    while len(fotos) > _MAXIMO_DE_FOTOS:
        fotos.popitem(last=False)

    if not pedidos:
        raise ValueError(
            f"A situação dos clientes começa em {ANO_INICIO_SITUACAO} (as compras "
            "começam em 2020, e o 1º ano serve pra contar os dias sem comprar)."
        )

    # Mais recente primeiro: numa lista de clientes, o que vem junto com
    # cada um (dias sem comprar, última compra) é da foto mais nova.
    return pd.concat([fotos[mes] for mes in reversed(pedidos)], ignore_index=True)


# O motor passa os filtros do período pra cá (ver orquestrador.buscar_dados_brutos).
carregar_situacao_clientes.recebe_filtros = True
