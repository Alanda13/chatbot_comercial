"""
Situação dos clientes (ativo, em risco, inativo, novo, recuperado).

Contada em dias, pelas compras do cliente em QUALQUER filial:
- ativo: comprou há menos de 90 dias (os 90 dias do WinThor:
  PCCONSUM.NUMDIASCLIINATIV);
- em risco de perda: de 60 a 89 dias sem comprar (continua ativo);
- inativo: de 90 dias a 1 ano sem comprar;
- parado há mais de 1 ano: contado à parte;
- novo: a 1ª compra (desde 2020) foi no período (o mês, ou os dias
  pedidos);
- recuperado: no período, voltou a comprar depois de 90 dias ou mais parado
  (DIAS_PARADO_ANTES_DE_VOLTAR guarda quanto tempo ficou parado, de
  qualquer tamanho);
- frequência de compra: quantas vezes o cliente comprou no período pedido
  (um ano: de janeiro até o fim dele ou hoje; um mês passado: só ele; sem
  período ou no mês atual: o ano atual até hoje) e a média por mês —
  compras no mesmo dia = 1; sem compra no período, fica vazia — em todas as
  filiais e, à parte, só naquela filial (como os dias sem comprar). Da
  empresa (colunas _DA_EMPRESA): os dias em que QUALQUER loja dela comprou.

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
mês (a situação no último dia; no mês atual, hoje) — ou de um período em
dias ("hoje", "semana passada": a situação no último dia dele, e novos,
recuperados e frequência só desses dias) — é montada na memória só
quando uma pergunta pede aquele período.
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
from core.repositories.filiais_repository import LOJAS, codigos_das_lojas, padronizar_filiais
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


def _primeira_compra(compras: pd.DataFrame) -> pd.Series:
    """Dia da 1ª compra de cada cliente desde 2020."""
    return compras.groupby("CODCLI")["DATA"].min()


def _voltas(compras: pd.DataFrame) -> pd.DataFrame:
    """Cada dia de compra (CODCLI, DATA) com quanto tempo o cliente ficou
    parado antes dela (DIAS_PARADO_ANTES_DE_VOLTAR, de qualquer tamanho:
    "voltou depois de 2 meses parado" também responde). Recuperado = 90
    dias ou mais."""
    dias = compras[["CODCLI", "DATA"]].drop_duplicates().sort_values(["CODCLI", "DATA"])
    parado = (dias["DATA"] - dias.groupby("CODCLI")["DATA"].shift()).dt.days
    return dias.assign(DIAS_PARADO_ANTES_DE_VOLTAR=parado).dropna().astype(
        {"DIAS_PARADO_ANTES_DE_VOLTAR": "int64"}
    )


def _frequencia_de_compra(janela: pd.DataFrame, por: list[str] = ["CODCLI"]) -> pd.Series:
    """Por cliente (ou cliente e filial): nº de dias com compra."""
    return janela[[*por, "DATA"]].drop_duplicates().groupby(por)["DATA"].size()


def _meses_da_janela(desde: pd.Timestamp, referencia: pd.Timestamp) -> float:
    """Meses de `desde` até a referência, cada mês proporcional aos dias
    dele: 01/01 a 23/10 = 9 + 23/31 = 9,74; setembro inteiro = 1; uma
    semana de outubro = 7/31."""
    meses = 0.0
    inicio = desde

    while inicio <= referencia:
        fim_do_mes = inicio + pd.offsets.MonthEnd(0)
        fim = min(fim_do_mes, referencia)
        meses += ((fim - inicio).days + 1) / inicio.days_in_month
        inicio = fim_do_mes + pd.Timedelta(days=1)

    return meses


def _com_frequencia(
    foto: pd.DataFrame, ate: pd.DataFrame, referencia: pd.Timestamp, desde: pd.Timestamp | None = None
) -> pd.DataFrame:
    """Compras e compras por mês, geral e na filial, de `desde` até a
    referência (sem `desde`: de janeiro até ela). Com EMPRESA na foto,
    também as da empresa (cliente sem empresa: as dele)."""
    if desde is None:
        desde = pd.Timestamp(referencia.year, 1, 1)

    janela = ate[(ate["DATA"] >= desde) & (ate["DATA"] <= referencia)]
    # Período menor que um mês (ex: uma semana): sem média por mês — 1 compra
    # num dia daria "31 por mês".
    meses = _meses_da_janela(desde, referencia)
    meses = meses if meses >= 1 else float("nan")
    unidades = {"CODCLI": ("FREQUENCIA_DE_COMPRA", "COMPRAS_POR_MES", "FREQUENCIA_NA_FILIAL", "COMPRAS_POR_MES_NA_FILIAL")}
    chaves = foto[["CODCLI", "CODFILIAL"]].copy()

    if "EMPRESA" in foto.columns:
        chaves["EMPRESA"] = foto["EMPRESA"].astype(object).fillna(foto["CODCLI"].astype(str))
        empresa_do_cliente = chaves.drop_duplicates("CODCLI").set_index("CODCLI")["EMPRESA"]
        janela = janela.assign(EMPRESA=janela["CODCLI"].map(empresa_do_cliente))
        unidades["EMPRESA"] = (
            "FREQUENCIA_DA_EMPRESA", "COMPRAS_POR_MES_DA_EMPRESA",
            "FREQUENCIA_DA_EMPRESA_NA_FILIAL", "COMPRAS_POR_MES_DA_EMPRESA_NA_FILIAL",
        )

    for unidade, (vezes, por_mes, vezes_na_filial, por_mes_na_filial) in unidades.items():
        geral = chaves[unidade].map(_frequencia_de_compra(janela, [unidade]))
        na_filial = _frequencia_de_compra(janela, [unidade, "CODFILIAL"]).reindex(
            pd.MultiIndex.from_frame(chaves[[unidade, "CODFILIAL"]])
        ).to_numpy()
        foto[vezes] = geral
        foto[por_mes] = (geral / meses).round(2)
        foto[vezes_na_filial] = na_filial
        foto[por_mes_na_filial] = (na_filial / meses).round(2)

    return foto


def _inicio_da_janela(ano: int, mes: int, filtros: dict | None, hoje: date) -> pd.Timestamp:
    """Início das compras da frequência na foto (ano, mês): o do período
    pedido — o 1º mês pedido (até este) — ou janeiro (um ano, sem período
    ou só no mês atual)."""
    meses = sorted(int(m) for m in (filtros or {}).get("mes") or [])

    if not meses or (meses == [mes] and (ano, mes) == (hoje.year, hoje.month)):
        return pd.Timestamp(ano, 1, 1)

    return pd.Timestamp(ano, min([m for m in meses if m <= mes] or [mes]), 1)


def _dias_dos_filtros(filtros: dict | None, hoje: date) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """Período em dias (filtro "dia"): início e fim, o fim até hoje."""
    dia = (filtros or {}).get("dia")

    if not dia:
        return None

    inicio = pd.Timestamp(str(dia["data_inicial"])[:10])
    fim = pd.Timestamp(str(dia.get("data_final") or dia["data_inicial"])[:10])
    return inicio, min(fim, pd.Timestamp(hoje))


def periodo_da_frequencia(filtros: dict | None, hoje: date | None = None) -> str | None:
    """As datas das compras que a frequência usou na foto mais recente do
    período ("01/01/2026 a 22/10/2026") — pra resposta não fazer conta de data."""
    hoje = hoje or date.today()
    dias = _dias_dos_filtros(filtros, hoje)

    if dias:
        return f"{dias[0]:%d/%m/%Y} a {dias[1]:%d/%m/%Y}"

    pedidos = meses_validos(_meses_dos_filtros(filtros, hoje), hoje)

    if not pedidos:
        return None

    ano, mes = pedidos[-1]
    referencia = _referencia(ano, mes, hoje)
    desde = _inicio_da_janela(ano, mes, filtros, hoje)
    return f"{desde:%d/%m/%Y} a {referencia:%d/%m/%Y}"


def _foto(
    compras: pd.DataFrame, inicio: pd.Timestamp, referencia: pd.Timestamp,
    primeira_compra: pd.Series, voltas: pd.DataFrame, desde_da_frequencia: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """A situação na referência; novos e recuperados de `inicio` até ela."""
    ate = compras[compras["DATA"] <= referencia].sort_values("DATA")

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
    foto["DATA_DA_FOTO"] = referencia
    foto["DIAS_SEM_COMPRAR"] = dias
    foto["ATIVO"] = ativo
    foto["EM_RISCO"] = ativo & (dias >= DIAS_EM_RISCO)
    foto["INATIVO"] = ~ativo & ~parado_ha_mais_de_1_ano
    foto["PARADO_HA_MAIS_DE_1_ANO"] = parado_ha_mais_de_1_ano
    foto["NOVO"] = foto["CODCLI"].map(primeira_compra).between(inicio, referencia)
    # O maior tempo parado antes de uma compra do período; sem compra nele
    # (ou só a 1ª): 0.
    no_periodo = voltas[voltas["DATA"].between(inicio, referencia)]
    foto["DIAS_PARADO_ANTES_DE_VOLTAR"] = foto["CODCLI"].map(
        no_periodo.groupby("CODCLI")["DIAS_PARADO_ANTES_DE_VOLTAR"].max()
    ).fillna(0).astype("int64")
    foto["RECUPERADO"] = foto["DIAS_PARADO_ANTES_DE_VOLTAR"] >= DIAS_INATIVO
    foto = _com_frequencia(foto, ate, referencia, desde_da_frequencia)
    foto["DIAS_SEM_COMPRAR_NA_FILIAL"] = (referencia - foto["ULTIMA_NA_FILIAL"]).dt.days
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
    "DIAS_SEM_COMPRAR", "DIAS_PARADO_ANTES_DE_VOLTAR",
    "FREQUENCIA_DE_COMPRA", "COMPRAS_POR_MES", "FREQUENCIA_NA_FILIAL", "COMPRAS_POR_MES_NA_FILIAL",
    "DIAS_SEM_COMPRAR_NA_FILIAL",
    "DATA_ULTIMA_COMPRA", "FILIAL_ULTIMA_COMPRA", "RCA_ULTIMA_COMPRA", "DATA_DA_FOTO",
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
    compras: pd.DataFrame, meses: list[tuple[int, int]], hoje: date | None = None,
    dias: tuple[pd.Timestamp, pd.Timestamp] | None = None,
) -> pd.DataFrame:
    """A foto de cada mês pedido (ano, mês) — ou, com `dias` (início, fim),
    a de um período em dias (a frequência também só dele)."""
    hoje = hoje or date.today()
    primeira_compra = _primeira_compra(compras)
    voltas = _voltas(compras)
    periodos = [dias] if dias else [
        (pd.Timestamp(ano, mes, 1), _referencia(ano, mes, hoje)) for ano, mes in meses_validos(meses, hoje)
    ]
    fotos = [
        _foto(compras, inicio, referencia, primeira_compra, voltas, inicio if dias else None)
        for inicio, referencia in periodos
    ]

    if not fotos:
        return pd.DataFrame(columns=COLUNAS_SITUACAO)

    situacao = pd.concat(fotos, ignore_index=True)[COLUNAS_SITUACAO]
    situacao[_MARCAS] = situacao[_MARCAS].astype("int8")
    return situacao


# Uma rede (ex: 45 lojas) pode ter muitas notas no mesmo dia.
_MAXIMO_DE_TEXTOS = 3


def _juntar_textos(valores: pd.Series) -> str:
    """"123", "123 e 456", "123, 456 e 789", "123, 456, 789 e mais 2" — sem
    repetir."""
    textos = list(dict.fromkeys(str(valor) for valor in valores.dropna()))

    if len(textos) > _MAXIMO_DE_TEXTOS:
        return f"{', '.join(textos[:_MAXIMO_DE_TEXTOS])} e mais {len(textos) - _MAXIMO_DE_TEXTOS}"

    return " e ".join([", ".join(textos[:-1]), textos[-1]]) if len(textos) > 1 else "".join(textos)


def _moeda(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _resumo_das_notas(do_dia: pd.DataFrame, chaves: list[str], sufixo: str = "") -> pd.DataFrame:
    """Por chave: valor somado e nota(s), pedido(s), RCA(s) (e filial(is),
    se vierem) juntos em texto."""
    textos = {
        coluna: nome + sufixo for coluna, nome in (
            ("NUMNOTA", "NOTA_ULTIMA_COMPRA"), ("NUMPED", "PEDIDO_ULTIMA_COMPRA"),
            ("NOME_RCA", "NOME_RCA_ULTIMA_COMPRA"), ("NOME_FILIAL", "FILIAL_ULTIMA_COMPRA"),
        )
        if coluna in do_dia.columns
    }
    # Quase todo mundo tem 1 nota no dia: só os outros passam por
    # _juntar_textos (um por um seria lento).
    varias = do_dia.groupby(chaves)["NUMNOTA"].transform("size") > 1
    resumo = pd.concat([
        do_dia[~varias].set_index(chaves)[list(textos)].astype({"NUMNOTA": str, "NUMPED": str}),
        do_dia[varias].groupby(chaves)[list(textos)].agg(_juntar_textos),
    ]).rename(columns=textos)
    resumo["VALOR_ULTIMA_COMPRA" + sufixo] = do_dia.groupby(chaves)["VENDA_BRUTA"].sum().map(_moeda)
    return resumo


def detalhes_da_ultima_compra(situacao: pd.DataFrame, vendas: pd.DataFrame) -> pd.DataFrame:
    """
    Valor, nota(s), pedido(s) e RCA(s) das notas do dia da última compra
    de cada cliente (ver o começo do arquivo), em texto. Com EMPRESA: também
    os da empresa (sufixo _EMPRESA) — o último dia em que alguma loja dela
    comprou, com TODAS as lojas que compraram nesse dia (valor somado).
    """
    chaves = ["CODCLI", "DATA_ULTIMA_COMPRA"]
    colunas = ["CODCLI", "DATA", "NUMNOTA", "NUMPED", "NOME_RCA", "VENDA_BRUTA"]
    do_dia = vendas[colunas].merge(
        situacao[chaves].drop_duplicates(), left_on=["CODCLI", "DATA"], right_on=chaves
    )
    situacao = situacao.join(_resumo_das_notas(do_dia, chaves), on=chaves)

    if "EMPRESA" not in situacao.columns:
        return situacao

    por_empresa = ["ANO", "MES", "EMPRESA"]
    ultimo_dia = situacao.groupby(por_empresa, observed=True)["DATA_ULTIMA_COMPRA"].max().reset_index()
    empresa_do_cliente = situacao.drop_duplicates("CODCLI").set_index("CODCLI")["EMPRESA"]
    notas = vendas[[*colunas, "CODFILIAL"]].assign(
        EMPRESA=lambda notas: notas["CODCLI"].map(empresa_do_cliente),
        NOME_FILIAL=lambda notas: codigos_das_lojas(vendas, notas["CODFILIAL"]).map(
            lambda codigo: LOJAS.get(codigo, (f"código {codigo}",))[0]
        ),
    )
    do_dia = notas.merge(
        ultimo_dia, left_on=["EMPRESA", "DATA"], right_on=["EMPRESA", "DATA_ULTIMA_COMPRA"]
    )
    return situacao.join(_resumo_das_notas(do_dia, por_empresa, "_EMPRESA"), on=por_empresa)


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
    dados = situacao.sort_values(["ANO", "MES"], ascending=False, kind="stable")

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
    dados = detalhes_da_ultima_compra(dados, venda_repository.carregar_notas_dos_clientes())
    dados = padronizar_filiais(dados, dados["CODFILIAL"])
    detalhes = [
        f"{nome}{sufixo}"
        for nome in ("VALOR_ULTIMA_COMPRA", "NOTA_ULTIMA_COMPRA", "PEDIDO_ULTIMA_COMPRA", "NOME_RCA_ULTIMA_COMPRA")
        for sufixo in ("", "_EMPRESA")
    ]
    return dados.astype({
        coluna: "category" for coluna in ("FILIAL", "ESTADO", "FILIAL_ULTIMA_COMPRA_EMPRESA", *detalhes)
    })


# As compras (e quem voltou a comprar) ficam em memória até o arquivo mudar;
# cada foto pedida também (~1 s pra montar), até o arquivo mudar ou o dia
# virar — no máximo as 24 mais recentes pedidas.
_MAXIMO_DE_FOTOS = 24
_cache: dict = {"versao": None, "compras": None, "fotos": OrderedDict(), "com_periodo": {}}


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
        # Os códigos somados numa loja (ex: 30 → 24, CD 33 → loja do
        # supervisor) contam como a mesma filial.
        compras["CODFILIAL"] = codigos_das_lojas(compras, compras["CODFILIAL"])
        _cache.update(versao=versao, compras=compras, fotos=OrderedDict(), com_periodo={})

    dias = _dias_dos_filtros(filtros, hoje)

    if dias:
        return _foto_dos_dias(*dias, hoje)

    fotos = _cache["fotos"]
    pedidos = meses_validos(_meses_dos_filtros(filtros, hoje), hoje)
    faltando = [mes for mes in pedidos if mes not in fotos]

    if faltando:
        montadas = _para_consulta(montar_situacao(_cache["compras"], faltando, hoje))

        # A frequência da empresa precisa do cadastro (EMPRESA), que só
        # entra em _para_consulta.
        for ano, mes in faltando:
            fotos[(ano, mes)] = _com_frequencia(
                montadas[(montadas["ANO"] == ano) & (montadas["MES"] == mes)].copy(),
                _cache["compras"], _referencia(ano, mes, hoje),
            )

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
    # cada um (dias sem comprar, última compra) é da foto mais nova. A foto
    # guardada traz a frequência desde janeiro; com outro início, a dele.
    partes = []

    for ano, mes in reversed(pedidos):
        foto = fotos[(ano, mes)]
        desde = _inicio_da_janela(ano, mes, filtros, hoje)

        if desde != pd.Timestamp(ano, 1, 1):
            chave = (ano, mes, desde)

            # Guarda só as colunas da frequência (a foto inteira tem ~80 MB).
            if chave not in _cache["com_periodo"]:
                chaves = foto.columns.intersection(["CODCLI", "CODFILIAL", "EMPRESA"])
                _cache["com_periodo"][chave] = _com_frequencia(
                    foto[chaves].copy(), _cache["compras"], _referencia(ano, mes, hoje), desde,
                ).drop(columns=chaves)

            foto = foto.assign(**_cache["com_periodo"][chave])

        partes.append(foto)

    return pd.concat(partes, ignore_index=True)


def _foto_dos_dias(inicio: pd.Timestamp, fim: pd.Timestamp, hoje: date) -> pd.DataFrame:
    """A foto de um período em dias (guardada junto com as dos meses)."""
    if fim.year < ANO_INICIO_SITUACAO:
        raise ValueError(
            f"A situação dos clientes começa em {ANO_INICIO_SITUACAO} (as compras "
            "começam em 2020, e o 1º ano serve pra contar os dias sem comprar)."
        )

    fotos = _cache["fotos"]
    chave = ("dias", inicio, fim)

    if chave not in fotos:
        foto = _para_consulta(montar_situacao(_cache["compras"], [], hoje, dias=(inicio, fim)))
        fotos[chave] = _com_frequencia(foto, _cache["compras"], fim, inicio)

    fotos.move_to_end(chave)

    while len(fotos) > _MAXIMO_DE_FOTOS:
        fotos.popitem(last=False)

    return fotos[chave]


# O motor passa os filtros do período pra cá (ver orquestrador.buscar_dados_brutos).
carregar_situacao_clientes.recebe_filtros = True
