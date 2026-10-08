"""
Carregamento dos dados de desconto por cliente.

Dois CSVs, gerados juntos do Oracle e atualizados em segundo plano por
`core/services/atualizador_service.py` (mesma regra de `faturamento_data.py`):

- `desconto_cliente.csv`: desconto e faturamento de tabela por
  filial/ano/mês/RCA/supervisor/cliente, desde 2020 (~1,2 milhão de
  linhas). Só códigos e números — o nome do cliente não se repete em
  cada linha.
- `clientes.csv`: cadastro (PCCLIENT) dos clientes que aparecem no
  arquivo acima — nome, fantasia, CNPJ, cidade e a EMPRESA a que o
  cadastro pertence.

Empresa = início do CNPJ (8 primeiros dígitos, a "raiz"): todas as lojas
de uma empresa têm a mesma raiz e só mudam o final (ex: as 214 lojas do
Mateus Supermercados, Mix/Eletro/Hiper incluídas, começam com
03.995.515). Cliente sem CNPJ válido (pessoa física, CNPJ em branco ou
"00000000000000") não se junta com ninguém: vira uma empresa sozinho.

Fonte: `VIEW_VENDAS_RESUMO_FATURAMENTO`, mesmos filtros de venda válida
e mesma conta de desconto do faturamento mensal (igual à rotina 8302).
"""
import re
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd

from core.repositories.arquivos_repository import (
    antes_da_janela_mensal,
    garantir,
    gravar_csv,
    inicio_da_janela_parcial,
    ler_csv,
)
from core.repositories.oracle import get_connection
from core.repositories.faturamento_repository import (
    ANO_INICIO_PADRAO,
    RAIZ_PROJETO,
    _FILTRO_VENDA_VALIDA,
    juntar_devolucao,
)
from core.repositories.filiais_repository import padronizar_filiais
from core.logger import obter_logger

logger = obter_logger(__name__)

ARQUIVO_DESCONTO_CLIENTE = RAIZ_PROJETO / "dados" / "desconto_cliente.csv"
ARQUIVO_CLIENTES = RAIZ_PROJETO / "dados" / "clientes.csv"

COLUNAS_DESCONTO = [
    "CODFILIAL", "ANO", "MES", "COD_RCA", "COD_SUPERVISOR", "CODCLI",
    "VALORDESC", "VENDA_TABELA", "VENDA_BRUTA", "VALOR_DEV", "VENDA_LIQ",
]
COLUNAS_CLIENTES = [
    "CODCLI", "CLIENTE", "FANTASIA", "CNPJ", "CIDADE", "UF",
    "EMPRESA", "NOME_EMPRESA", "CNPJ_EMPRESA", "VENDA_TOTAL",
]


def _consultar_desconto(cursor, desde: date) -> pd.DataFrame:
    cursor.arraysize = 10000
    cursor.execute(
        f"""
        SELECT V.CODFILIAL, EXTRACT(YEAR FROM V.DTSAIDA) ANO,
               EXTRACT(MONTH FROM V.DTSAIDA) MES, V.CODUSUR COD_RCA,
               V.CODSUPERVISOR COD_SUPERVISOR, V.CODCLI,
               ROUND(SUM(V.VLDESCONTO * V.QT), 4) VALORDESC,
               ROUND(SUM(V.VLTABELA), 2) VENDA_TABELA,
               ROUND(SUM(V.VLVENDA), 2) VENDA_BRUTA
        FROM VIEW_VENDAS_RESUMO_FATURAMENTO V
        WHERE V.DTSAIDA >= :desde
        {_FILTRO_VENDA_VALIDA}
        GROUP BY V.CODFILIAL, EXTRACT(YEAR FROM V.DTSAIDA),
                 EXTRACT(MONTH FROM V.DTSAIDA), V.CODUSUR,
                 V.CODSUPERVISOR, V.CODCLI
        """,
        desde=desde,
    )
    colunas = [d[0] for d in cursor.description]
    return pd.DataFrame(cursor.fetchall(), columns=colunas)


def _consultar_cadastro(cursor) -> pd.DataFrame:
    cursor.arraysize = 10000
    cursor.execute(
        """
        SELECT CODCLI, TRIM(CLIENTE) CLIENTE, TRIM(FANTASIA) FANTASIA,
               CGCENT CNPJ, TRIM(MUNICENT) CIDADE, TRIM(ESTENT) UF
        FROM PCCLIENT
        """
    )
    colunas = [d[0] for d in cursor.description]
    return pd.DataFrame(cursor.fetchall(), columns=colunas)


def identificar_empresa(codcli: int, cnpj) -> str:
    """
    A quem o cadastro pertence:
    - CNPJ válido (14 dígitos, não todos iguais): a raiz (8 primeiros
      dígitos) — junta as lojas da empresa;
    - CPF (11 dígitos, não zerado): o CPF inteiro — junta a mesma pessoa
      cadastrada mais de uma vez (172 casos) e os 5 cadastros "CONSUMIDOR
      FINAL", que usam todos o CPF 111.111.111-11 (entre quem comprou
      desde 2020, só eles usam esse CPF);
    - senão "CLI<código>": o cliente fica sozinho.
    """
    digitos = re.sub(r"\D", "", str(cnpj or ""))

    if len(digitos) == 14 and len(set(digitos)) > 1:
        return digitos[:8]

    if len(digitos) == 11 and set(digitos) != {"0"}:
        return digitos

    return f"CLI{codcli}"


def _cnpj_da_empresa(empresa: str, cnpj) -> str:
    """
    Documento que identifica a empresa: início do CNPJ (03.995.515), CPF
    (111.111.111-11) ou, cliente sozinho, o que estiver no cadastro.
    """
    if empresa.startswith("CLI"):
        return str(cnpj or "")

    if len(empresa) == 11:
        return f"{empresa[:3]}.{empresa[3:6]}.{empresa[6:9]}-{empresa[9:]}"

    return f"{empresa[:2]}.{empresa[2:5]}.{empresa[5:]}"


def _nome_da_empresa(clientes: pd.DataFrame) -> pd.Series:
    """
    Nome que representa a empresa: a razão social mais usada entre os
    cadastros dela (o mesmo nome aparece escrito de vários jeitos, ex:
    "MATEUS SUPERMERCADOS S A" / "S.A." / "SA").
    """
    return clientes.groupby("EMPRESA")["CLIENTE"].agg(
        lambda nomes: nomes.fillna("").value_counts().index[0]
    )


def _buscar(desde: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Desconto por cliente desde `desde` + o cadastro inteiro (PCCLIENT)."""
    conexao = get_connection()

    try:
        cursor = conexao.cursor()
        desconto = juntar_devolucao(
            _consultar_desconto(cursor, desde), cursor, desde,
            {"COD_RCA": "CODUSUR", "COD_SUPERVISOR": "CODSUPERVISOR", "CODCLI": "CODCLI"},
        )
        cadastro = _consultar_cadastro(cursor)
    finally:
        conexao.close()

    desconto["CODCLI"] = desconto["CODCLI"].astype(int)

    return desconto[COLUNAS_DESCONTO], cadastro


def _montar_clientes(cadastro: pd.DataFrame, desconto: pd.DataFrame) -> pd.DataFrame:
    """Cadastro de quem aparece no desconto, com empresa, nome e CNPJ dela."""
    clientes = cadastro[cadastro["CODCLI"].isin(desconto["CODCLI"])].copy()
    clientes["CODCLI"] = clientes["CODCLI"].astype(int)
    clientes["EMPRESA"] = [
        identificar_empresa(codcli, cnpj)
        for codcli, cnpj in zip(clientes["CODCLI"], clientes["CNPJ"])
    ]
    clientes["NOME_EMPRESA"] = clientes["EMPRESA"].map(_nome_da_empresa(clientes))
    clientes["CNPJ_EMPRESA"] = [
        _cnpj_da_empresa(empresa, cnpj)
        for empresa, cnpj in zip(clientes["EMPRESA"], clientes["CNPJ"])
    ]
    # Venda de tabela desde 2020 — só pra ordenar as opções quando um
    # nome acha várias empresas (a que mais compra aparece primeiro).
    clientes["VENDA_TOTAL"] = clientes["CODCLI"].map(
        desconto.groupby("CODCLI")["VENDA_TABELA"].sum()
    ).fillna(0).round(2)

    return clientes[COLUNAS_CLIENTES]


def gerar_tabelas(
    ano_inicio: int = ANO_INICIO_PADRAO,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    desconto, cadastro = _buscar(date(ano_inicio, 1, 1))
    return desconto, _montar_clientes(cadastro, desconto)


def atualizar(completa: bool) -> None:
    """
    Completa: tudo desde 2020. Parcial: busca no Oracle só o mês atual e
    o anterior (o pico de memória de ~500 MB da completa some) e junta com
    os meses mais antigos do CSV; o cadastro é refeito inteiro (cliente
    novo, CNPJ corrigido).
    """
    if completa or not (ARQUIVO_DESCONTO_CLIENTE.exists() and ARQUIVO_CLIENTES.exists()):
        desconto, clientes = gerar_tabelas()
    else:
        desde = inicio_da_janela_parcial()
        antigo = antes_da_janela_mensal(ler_csv(ARQUIVO_DESCONTO_CLIENTE), desde)
        novo, cadastro = _buscar(desde)
        desconto = pd.concat([antigo, novo], ignore_index=True)
        clientes = _montar_clientes(cadastro, desconto)

    gravar_csv(clientes, ARQUIVO_CLIENTES)
    gravar_csv(desconto, ARQUIVO_DESCONTO_CLIENTE)


def _garantir() -> None:
    garantir(
        [ARQUIVO_DESCONTO_CLIENTE, ARQUIVO_CLIENTES], atualizar, "desconto por cliente"
    )


def carregar_clientes() -> pd.DataFrame:
    """Cadastro dos clientes que compraram desde 2020 (ver docstring)."""
    _garantir()
    # EMPRESA como texto: a raiz "03995515" lida como número perderia o 0.
    return ler_csv(ARQUIVO_CLIENTES, dtype={"EMPRESA": str, "CNPJ": str})


def carregar_desconto_cliente() -> pd.DataFrame:
    """
    Desconto por filial/mês/RCA/cliente, já com os dados do cadastro
    (nome, CNPJ, cidade, empresa) juntados pelo código do cliente.
    """
    _garantir()
    dados = ler_csv(ARQUIVO_DESCONTO_CLIENTE)
    dados = dados.merge(carregar_clientes(), on="CODCLI", how="left")
    return padronizar_filiais(dados, dados["CODFILIAL"])


# Máximo de empresas listadas quando um nome acha várias (ex: "Mateus"
# também acha pessoas físicas com esse nome) — as que mais compram
# primeiro; o resto vira "e mais N".
_MAX_OPCOES_EMPRESA = 10


def _normalizar(texto) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or "").upper())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", texto).split())


def _empresas_pelo_nome(nome: str) -> pd.DataFrame:
    """
    Empresas com algum cadastro cujo nome ou fantasia contém o nome
    procurado — uma linha por empresa, a que mais compra primeiro.
    """
    clientes = carregar_clientes()
    procurado = _normalizar(nome)
    achou = clientes["CLIENTE"].map(_normalizar).str.contains(procurado, regex=False) | (
        clientes["FANTASIA"].map(_normalizar).str.contains(procurado, regex=False)
    )
    empresas = clientes[clientes["EMPRESA"].isin(clientes.loc[achou, "EMPRESA"])]

    return (
        empresas.groupby(["EMPRESA", "NOME_EMPRESA", "CNPJ_EMPRESA"])
        .agg(LOJAS=("CODCLI", "count"), VENDA_TOTAL=("VENDA_TOTAL", "sum"))
        .reset_index()
        .sort_values("VENDA_TOTAL", ascending=False)
    )


def _descrever_opcao(linha) -> str:
    if len(linha.EMPRESA) == 8:
        lojas = f"{linha.LOJAS} lojas, todas somadas" if linha.LOJAS > 1 else "1 loja"
        return f"{linha.NOME_EMPRESA} (CNPJ {linha.CNPJ_EMPRESA}, {lojas})"

    if len(linha.EMPRESA) == 11:
        return f"{linha.NOME_EMPRESA} (pessoa física, CPF {linha.CNPJ_EMPRESA})"

    return f"{linha.NOME_EMPRESA} (sem CNPJ/CPF, código do cliente {linha.EMPRESA[3:]})"


def _descrever_opcoes(empresas: pd.DataFrame) -> str:
    linhas = [
        f"{numero}. {_descrever_opcao(linha)}"
        for numero, linha in enumerate(
            empresas.head(_MAX_OPCOES_EMPRESA).itertuples(), start=1
        )
    ]
    resto = len(empresas) - _MAX_OPCOES_EMPRESA

    if resto > 0:
        linhas.append(f"e mais {resto} com nomes parecidos")

    return "; ".join(linhas)


def resolver_empresas(nome_ou_codigo, filiais=None) -> list[str]:
    """
    Resolve o que o usuário informou para a(s) EMPRESA(s) — o início do
    CNPJ, que junta todas as lojas:
    - início do CNPJ (8 dígitos, com ou sem pontos) ou CNPJ inteiro
      (14 dígitos): a empresa dele;
    - "CLI<código>" (empresa de um cliente sem CNPJ): ela mesma;
    - outro número: código de cliente — a empresa desse cliente;
    - nome: procurado no nome e no nome fantasia dos cadastros. Se achar
      uma empresa só, é ela; se achar várias (ex: "Vanguarda" acha a
      distribuidora e a construtora), levanta erro listando as opções,
      pro usuário escolher — nunca soma empresas diferentes sozinho.
    `filiais` é aceito pela mesma assinatura do resolvedor de RCA, mas
    não é usado: a filial filtra as vendas, não o cadastro.
    """
    texto = str(nome_ou_codigo).strip()
    digitos = re.sub(r"\D", "", texto)
    clientes = carregar_clientes()

    if texto.upper().startswith("CLI") and texto[3:].isdigit():
        empresa = texto.upper()
        if empresa not in set(clientes["EMPRESA"]):
            raise ValueError(f"A empresa '{texto}' não foi encontrada.")
        return [empresa]

    if digitos and len(digitos) == len(re.sub(r"[\s./-]", "", texto)):
        if len(digitos) in (8, 11, 14):
            empresa = digitos if len(digitos) == 11 else digitos[:8]
            if empresa not in set(clientes["EMPRESA"]):
                raise ValueError(
                    f"Nenhum cliente com o CPF/CNPJ {texto} comprou desde 2020."
                )
            return [empresa]

        return [
            clientes.loc[clientes["CODCLI"] == codigo, "EMPRESA"].iloc[0]
            for codigo in resolver_codigos_cliente(texto)
        ]

    empresas = _empresas_pelo_nome(texto)

    if empresas.empty:
        raise ValueError(f"O cliente '{texto}' não foi encontrado.")

    if len(empresas) > 1:
        raise ValueError(
            f"Encontrei mais de uma empresa com '{texto}' no nome: "
            f"{_descrever_opcoes(empresas)}. Mostre essa lista numerada ao "
            "usuário (com o CNPJ/CPF de cada um) e pergunte qual (ou "
            "quais) ele quer; ele pode responder pelo número, pelo nome ou "
            "pelo CNPJ/CPF. Depois consulte de novo com o CNPJ/CPF "
            "escolhido no filtro 'empresa'."
        )

    return [empresas["EMPRESA"].iloc[0]]


def resolver_codigos_cliente(nome_ou_codigo, filiais=None) -> list[int]:
    """
    Código do cliente = UMA loja (um cadastro). Um nome, em vez de
    código, vira todas as lojas da empresa encontrada (mesma busca de
    `resolver_empresas`, inclusive o erro com as opções).
    """
    texto = str(nome_ou_codigo).strip()
    clientes = carregar_clientes()

    if texto.isdigit():
        codigo = int(texto)
        if codigo not in set(clientes["CODCLI"]):
            raise ValueError(
                f"O cliente de código {codigo} não foi encontrado (ou não "
                "comprou desde 2020)."
            )
        return [codigo]

    empresas = resolver_empresas(texto)
    return clientes.loc[clientes["EMPRESA"].isin(empresas), "CODCLI"].tolist()
