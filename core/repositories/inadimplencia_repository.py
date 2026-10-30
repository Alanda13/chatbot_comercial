"""
Inadimplência: os títulos a receber vencidos e não pagos.

Fonte: a view FNORTE.GFN_VIEW_CONTAS_RECEBER_8188 (espelho da rotina 120,
sem os títulos cancelados e desdobrados). Valor = o do título (VALOR),
cartão incluído. Como na base e no BI da controladoria, ficam de fora os
valores negativos (estornos, ESTR) e as cobranças que não são dívida do
cliente (COBRANCAS_FORA: devolução, bonificação, crédito, desdobrado).

Duas leituras dos mesmos títulos, pelo mês de VENCIMENTO:
- inadimplência oficial (fechamento da controladoria): todo dia 10 fecha o
  mês de 2 meses atrás — o de 10/10 conta os títulos vencidos em agosto
  ainda em aberto em 10/10. Mês sem fechamento ainda fica de fora. O % é
  esse valor ÷ o faturamento líquido da filial no mês;
- em atraso hoje: vencidos e não pagos agora, com os dias de atraso.
  Risco de bloqueio (o cliente é bloqueado com 30 dias de atraso): o
  título mais atrasado do cliente tem de 20 a 29 dias.

Um CSV, gerado do Oracle e atualizado em segundo plano por
`core/services/atualizador_service.py`: `titulos_receber.csv` — os títulos
vencidos em aberto e os pagos só depois do fechamento do mês deles (eles
estavam em aberto no dia 10). Quem é oficial, quem está em atraso e os
dias contam a partir de hoje, na leitura.
"""
from datetime import date, timedelta

import pandas as pd

from core.repositories.arquivos_repository import garantir, gravar_csv, ler_csv
from core.repositories import cliente_repository
from core.repositories.faturamento_repository import RAIZ_PROJETO, carregar_faturamento_mensal
from core.repositories.filiais_repository import codigos_das_lojas, padronizar_filiais
from core.repositories.rca_repository import carregar_cadastro

ARQUIVO_TITULOS_RECEBER = RAIZ_PROJETO / "data" / "titulos_receber.csv"

DIA_DO_FECHAMENTO = 10
MESES_ATE_O_FECHAMENTO = 2
DIAS_PARA_BLOQUEIO = 30
DIAS_EM_RISCO_DE_BLOQUEIO = 20
# As mesmas do BI da controladoria (medida Valor_Inadimplência_v2).
COBRANCAS_FORA = ("DEVP", "DEVT", "BNF", "BNFT", "BNFR", "BNTR", "BNRP", "CRED", "DESD")

COLUNAS_TITULOS = [
    "CODFILIAL", "CODCLI", "CLIENTE", "CNPJ", "CIDADE", "COD_RCA", "CODCOB",
    "DUPLIC", "PREST", "DTEMISSAO", "DTVENC", "DTPAG", "VALOR",
]
_DATAS = ["DTEMISSAO", "DTVENC", "DTPAG"]


def atualizar(completa: bool) -> None:
    """O arquivo é pequeno (~19 mil títulos): sempre lido inteiro."""
    from core.repositories.oracle import get_connection

    cobrancas_fora = ", ".join(f"'{cobranca}'" for cobranca in COBRANCAS_FORA)
    conexao = get_connection()

    try:
        cursor = conexao.cursor()
        cursor.arraysize = 20000
        cursor.execute(
            f"""
            SELECT CODFILIAL, CODCLI, CLIENTE, CNPJ, NOMECIDADE CIDADE,
                   RCA COD_RCA, CODCOB, DUPLIC, PREST, DTEMISSAO, DTVENC,
                   DTPAG, VALOR
            FROM FNORTE.GFN_VIEW_CONTAS_RECEBER_8188
            WHERE DTVENC < TRUNC(SYSDATE)
              AND VALOR > 0
              AND NVL(TRIM(CODCOB), '-') NOT IN ({cobrancas_fora})
              AND (DTPAG IS NULL
                   OR DTPAG > ADD_MONTHS(TRUNC(DTVENC, 'MM'), {MESES_ATE_O_FECHAMENTO})
                              + {DIA_DO_FECHAMENTO - 1})
            """
        )
        dados = pd.DataFrame(cursor.fetchall(), columns=[d[0] for d in cursor.description])
    finally:
        conexao.close()

    # A filial é texto na view.
    dados["CODFILIAL"] = dados["CODFILIAL"].astype("int64")
    gravar_csv(dados[COLUNAS_TITULOS], ARQUIVO_TITULOS_RECEBER)


def _ler_titulos() -> pd.DataFrame:
    garantir([ARQUIVO_TITULOS_RECEBER], atualizar, "títulos a receber")
    dados = ler_csv(ARQUIVO_TITULOS_RECEBER, dtype={"CNPJ": str, "PREST": str})

    for coluna in _DATAS:
        dados[coluna] = pd.to_datetime(dados[coluna], format="ISO8601")

    return dados


def data_do_fechamento(ano: pd.Series, mes: pd.Series) -> pd.Series:
    """Dia em que cada mês de vencimento fecha: dia 10 de 2 meses depois
    (agosto → 10/10)."""
    meses = ano * 12 + mes - 1 + MESES_ATE_O_FECHAMENTO
    return pd.to_datetime(pd.DataFrame({"year": meses // 12, "month": meses % 12 + 1, "day": DIA_DO_FECHAMENTO}))


def ultimo_fechamento(hoje: date) -> pd.Timestamp:
    """O dia 10 mais recente até hoje."""
    dia = pd.Timestamp(hoje.year, hoje.month, DIA_DO_FECHAMENTO)
    return dia if pd.Timestamp(hoje) >= dia else dia - pd.DateOffset(months=1)


def marcar_situacao(titulos: pd.DataFrame, hoje: date) -> pd.DataFrame:
    """
    Cada título com o que o motor soma/conta (ver o começo do arquivo):
    VALOR/TITULO/CLIENTE_INADIMPLENTE (oficial), _EM_ATRASO (hoje),
    DIAS_DE_ATRASO, CLIENTE_EM_RISCO_DE_BLOQUEIO e DIAS_PARA_O_BLOQUEIO.
    Cliente nas colunas CLIENTE_*: o código quando ele está naquela
    situação (vazio quando não) — o motor conta os códigos diferentes.
    """
    hoje = pd.Timestamp(hoje)
    dados = titulos.assign(ANO=titulos["DTVENC"].dt.year, MES=titulos["DTVENC"].dt.month)
    fechamento = data_do_fechamento(dados["ANO"], dados["MES"])
    oficial = (fechamento <= hoje) & (dados["DTPAG"].isna() | (dados["DTPAG"] > fechamento))
    em_atraso = dados["DTPAG"].isna() & (dados["DTVENC"] < hoje)

    dados["VALOR_INADIMPLENTE"] = dados["VALOR"].where(oficial, 0.0)
    dados["TITULO_INADIMPLENTE"] = oficial.astype("int64")
    dados["CLIENTE_INADIMPLENTE"] = dados["CODCLI"].where(oficial).astype("Int64")
    dados["VALOR_EM_ATRASO"] = dados["VALOR"].where(em_atraso, 0.0)
    dados["TITULO_EM_ATRASO"] = em_atraso.astype("int64")
    dados["CLIENTE_EM_ATRASO"] = dados["CODCLI"].where(em_atraso).astype("Int64")
    dados["DIAS_DE_ATRASO"] = (hoje - dados["DTVENC"]).dt.days.where(em_atraso).astype("Int64")

    # O bloqueio é do cliente: vale o título mais atrasado dele, em
    # qualquer filial.
    mais_atrasado = dados["CODCLI"].map(dados.groupby("CODCLI")["DIAS_DE_ATRASO"].max())
    em_risco = em_atraso & mais_atrasado.between(DIAS_EM_RISCO_DE_BLOQUEIO, DIAS_PARA_BLOQUEIO - 1)
    dados["CLIENTE_EM_RISCO_DE_BLOQUEIO"] = dados["CODCLI"].where(em_risco).astype("Int64")
    dados["DIAS_PARA_O_BLOQUEIO"] = (DIAS_PARA_BLOQUEIO - mais_atrasado).where(em_risco).astype("Int64")
    return dados


def com_faturamento(dados: pd.DataFrame, faturamento: pd.DataFrame, hoje: date) -> pd.DataFrame:
    """
    FATURAMENTO_LIQ: o faturamento líquido da filial no mês, em cada título
    (o motor soma uma vez por filial/mês), só dos meses já fechados — o %
    compara a inadimplência oficial com o faturamento dos mesmos meses.
    Mês fechado sem nenhum título ganha uma linha sem título, pra o
    faturamento dele também entrar.
    """
    chave = ["CODFILIAL", "ANO", "MES"]
    por_mes = faturamento.groupby(chave, as_index=False)["VENDA_LIQ"].sum()
    por_mes = por_mes[data_do_fechamento(por_mes["ANO"], por_mes["MES"]) <= pd.Timestamp(hoje)]
    por_mes = por_mes.rename(columns={"VENDA_LIQ": "FATURAMENTO_LIQ"})

    sem_titulo = por_mes.merge(dados[chave].drop_duplicates(), how="left", indicator=True)
    sem_titulo = sem_titulo.loc[sem_titulo["_merge"] == "left_only", chave]
    zeros = {
        coluna: 0 for coluna in (
            "VALOR_INADIMPLENTE", "TITULO_INADIMPLENTE", "VALOR_EM_ATRASO", "TITULO_EM_ATRASO",
        )
    }
    dados = pd.concat([dados, sem_titulo.assign(**zeros)], ignore_index=True)
    return dados.merge(por_mes, on=chave, how="left")


def mes_do_ultimo_fechamento(hoje: date | None = None) -> tuple[int, int]:
    mes = ultimo_fechamento(hoje or date.today()) - pd.DateOffset(months=MESES_ATE_O_FECHAMENTO)
    return mes.year, mes.month


def _sem_periodo(filtros: dict | None) -> bool:
    return not any((filtros or {}).get(chave) for chave in ("ano", "mes", "dia"))


def so_o_ultimo_mes_fechado(dados: pd.DataFrame, hoje: date) -> pd.DataFrame:
    """Sem período na pergunta, o oficial (e o faturamento do %) é o do
    último mês fechado — a soma de todos os meses não é a inadimplência de
    nenhum relatório. O em atraso continua com todos os vencimentos; o
    título de outro mês que já foi pago sai (senão o cliente/RCA dele
    aparecia na lista, zerado)."""
    ano, mes = mes_do_ultimo_fechamento(hoje)
    outro_mes = (dados["ANO"] != ano) | (dados["MES"] != mes)
    dados = dados[~outro_mes | (dados["TITULO_EM_ATRASO"] == 1)].copy()
    outro_mes = outro_mes[dados.index]
    dados.loc[outro_mes, ["VALOR_INADIMPLENTE", "TITULO_INADIMPLENTE"]] = 0
    dados.loc[outro_mes, "CLIENTE_INADIMPLENTE"] = pd.NA
    dados.loc[outro_mes, "FATURAMENTO_LIQ"] = float("nan")
    return dados


def carregar_inadimplencia(filtros: dict | None = None) -> pd.DataFrame:
    """Os títulos prontos pro motor (ver o começo do arquivo), com o
    supervisor do RCA, a empresa do cliente e o faturamento do mês."""
    hoje = date.today()
    titulos = _ler_titulos()
    # O CD 33 vai pra loja do supervisor do RCA, como no faturamento.
    titulos["CODFILIAL"] = codigos_das_lojas(titulos, titulos["CODFILIAL"])
    dados = marcar_situacao(titulos, hoje)

    cadastro = carregar_cadastro().drop_duplicates("COD_RCA").set_index("COD_RCA")
    dados["COD_SUPERVISOR"] = dados["COD_RCA"].map(cadastro["COD_SUPERVISOR"])

    # Empresa do cadastro dos clientes; quem não comprou desde 2020 não está
    # nele: a empresa sai do CNPJ do título.
    empresas = cliente_repository.carregar_clientes()[["CODCLI", "EMPRESA", "NOME_EMPRESA", "CNPJ_EMPRESA"]]
    dados = dados.merge(empresas, on="CODCLI", how="left")
    sem_empresa = dados["EMPRESA"].isna()
    dados.loc[sem_empresa, "EMPRESA"] = [
        cliente_repository.identificar_empresa(codcli, cnpj)
        for codcli, cnpj in zip(dados.loc[sem_empresa, "CODCLI"], dados.loc[sem_empresa, "CNPJ"])
    ]
    dados.loc[sem_empresa, "NOME_EMPRESA"] = dados.loc[sem_empresa, "CLIENTE"]
    dados.loc[sem_empresa, "CNPJ_EMPRESA"] = [
        cliente_repository._cnpj_da_empresa(empresa, cnpj)
        for empresa, cnpj in zip(dados.loc[sem_empresa, "EMPRESA"], dados.loc[sem_empresa, "CNPJ"])
    ]

    dados = com_faturamento(dados, carregar_faturamento_mensal(), hoje)

    if _sem_periodo(filtros):
        dados = so_o_ultimo_mes_fechado(dados, hoje)

    return padronizar_filiais(dados, dados["CODFILIAL"])


# O motor passa os filtros do período pra cá (ver orquestrador.buscar_dados_brutos).
carregar_inadimplencia.recebe_filtros = True


_NOMES_DOS_MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
    "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def _periodo_sem_periodo(hoje: date) -> str:
    ano, mes = mes_do_ultimo_fechamento(hoje)
    return (
        f"a inadimplência oficial (valor, títulos, clientes e %) é a do último "
        f"mês fechado, {_NOMES_DOS_MESES[mes - 1]} de {ano}; o em atraso hoje "
        "junta todos os vencimentos"
    )


def descrever_sem_periodo(hoje: date | None = None) -> str:
    """O período de uma pergunta sem período (ver so_o_ultimo_mes_fechado),
    curto pra caber no meio da frase da resposta."""
    ano, mes = mes_do_ultimo_fechamento(hoje or date.today())
    return (
        f"sem filtro de período (oficial: {_NOMES_DOS_MESES[mes - 1]} de {ano}, "
        "último mês fechado; em atraso: situação de hoje)"
    )


def descrever_fechamento(filtros: dict | None = None, hoje: date | None = None) -> str:
    """O último fechamento e o próximo, prontos pra resposta — e, sem
    período, que o oficial é o do último mês fechado."""
    hoje = hoje or date.today()
    ultimo = ultimo_fechamento(hoje)
    fechado = ultimo - pd.DateOffset(months=MESES_ATE_O_FECHAMENTO)
    proximo = ultimo + pd.DateOffset(months=1)
    aberto = fechado + pd.DateOffset(months=1)
    texto = (
        f"Último fechamento: {ultimo:%d/%m/%Y} — vencimentos até "
        f"{_NOMES_DOS_MESES[fechado.month - 1]} de {fechado.year} fechados. "
        f"{_NOMES_DOS_MESES[aberto.month - 1].capitalize()} de {aberto.year} fecha em "
        f"{proximo:%d/%m/%Y}; vencimentos depois disso ainda não têm "
        "inadimplência oficial (só 'em atraso hoje'). Em atraso hoje = "
        f"vencidos até ontem ({hoje - timedelta(days=1):%d/%m/%Y}) e não pagos, "
        "dentro do período consultado, inclusive os meses que ainda não fecharam."
    )

    if _sem_periodo(filtros):
        texto += f" A pergunta não disse o período: {_periodo_sem_periodo(hoje)}."

    return texto
