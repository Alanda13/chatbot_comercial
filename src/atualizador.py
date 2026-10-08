"""
Atualiza os CSVs do Oracle em segundo plano — quem pergunta nunca espera.

Antes, o 1º a perguntar depois de 1 hora esperava o Oracle (06/10/2026:
~5 min, o diário e o mensal regerados um depois do outro). Agora:

- ao abrir o chatbot: atualização COMPLETA (desde 2020), em segundo plano
  — enquanto isso, as perguntas usam os CSVs que já existem;
- de hora em hora, das 7h às 19h: PARCIAL (só o mês atual e o anterior —
  mensal ~36 s em vez de ~159 s, diário ~9 s em vez de ~29 s);
- o 1º ciclo de cada dia (a partir das 7h) é COMPLETO: pega devoluções e
  cancelamentos em meses antigos, mantendo tudo igual ao WinThor;
- à noite não roda nada. Se o Oracle falhar, fica valendo o CSV anterior.

`iniciar()` é chamado pelo app.py; roda uma única vez por processo.
"""
import threading
import time
from datetime import datetime

from src.arquivos_oracle import com_tentativas, marcar_atualizador_ativo
from src.logger import obter_logger

logger = obter_logger(__name__)

HORA_INICIO = 7
HORA_FIM = 19
_SEGUNDOS_ENTRE_PARCIAIS = 3600
_SEGUNDOS_ENTRE_VERIFICACOES = 60

_trava_inicio = threading.Lock()
_iniciado = False
_atualizando = threading.Event()


def _bases():
    # Import aqui dentro: os módulos de dados importam src.arquivos_oracle,
    # e o atualizador só precisa deles quando roda.
    from src import cliente_data, faturamento_data, faturamento_diario_data, produto_data

    return [
        ("faturamento mensal", faturamento_data.atualizar,
         [faturamento_data.ARQUIVO_FATURAMENTO_MENSAL]),
        ("faturamento diário", faturamento_diario_data.atualizar,
         [faturamento_diario_data.ARQUIVO_FATURAMENTO_DIARIO]),
        ("faturamento por forma de pagamento", faturamento_diario_data.atualizar_forma_pagamento,
         [faturamento_diario_data.ARQUIVO_FATURAMENTO_DIARIO_FORMA_PAGAMENTO]),
        ("desconto por cliente", cliente_data.atualizar,
         [cliente_data.ARQUIVO_DESCONTO_CLIENTE, cliente_data.ARQUIVO_CLIENTES]),
        ("desconto por produto", produto_data.atualizar,
         [produto_data.ARQUIVO_DESCONTO_PRODUTO, produto_data.ARQUIVO_PRODUTOS]),
    ]


def rodar_atualizacao(completa: bool) -> None:
    """Atualiza todas as bases; a falha de uma não impede as outras."""
    _atualizando.set()
    tipo = "completa" if completa else "parcial"

    try:
        for descricao, atualizar, _ in _bases():
            inicio = time.time()
            try:
                com_tentativas(descricao, lambda: atualizar(completa))
                logger.info(
                    f"Atualização {tipo} de {descricao}: {time.time() - inicio:.0f} s"
                )
            except Exception:
                logger.exception(
                    f"Atualização {tipo} de {descricao} falhou — seguindo com o CSV anterior."
                )
    finally:
        _atualizando.clear()


def proxima_acao(
    agora: datetime, ultima_completa, ultima_parcial: float | None
) -> str | None:
    """
    "completa", "parcial" ou None. Separado do laço pra ser testável.
    - Nunca rodou completa (acabou de abrir): completa, a qualquer hora.
    - Dia novo, já no horário: completa.
    - No horário e 1 hora desde a última: parcial.
    """
    if ultima_completa is None:
        return "completa"

    no_horario = HORA_INICIO <= agora.hour < HORA_FIM

    if not no_horario:
        return None

    if ultima_completa != agora.date():
        return "completa"

    if ultima_parcial is None or time.time() - ultima_parcial >= _SEGUNDOS_ENTRE_PARCIAIS:
        return "parcial"

    return None


def _laco() -> None:
    ultima_completa = None
    ultima_parcial = time.time()

    while True:
        agora = datetime.now()
        acao = proxima_acao(agora, ultima_completa, ultima_parcial)

        if acao == "completa":
            rodar_atualizacao(completa=True)
            ultima_completa = agora.date()
            ultima_parcial = time.time()
        elif acao == "parcial":
            rodar_atualizacao(completa=False)
            ultima_parcial = time.time()

        time.sleep(_SEGUNDOS_ENTRE_VERIFICACOES)


def iniciar() -> None:
    global _iniciado

    with _trava_inicio:
        if _iniciado:
            return
        _iniciado = True

    marcar_atualizador_ativo()
    threading.Thread(target=_laco, name="atualizador-oracle", daemon=True).start()


def descrever_ultima_atualizacao() -> str | None:
    """
    "Dados atualizados em 06/10/2026 às 08:41" — a hora do CSV MAIS
    ANTIGO (o dado mais desatualizado que uma resposta pode ter usado).
    """
    arquivos = [arquivo for *_, lista in _bases() for arquivo in lista if arquivo.exists()]

    if not arquivos:
        return None

    momento = datetime.fromtimestamp(min(arquivo.stat().st_mtime for arquivo in arquivos))
    texto = f"Dados atualizados em {momento:%d/%m/%Y} às {momento:%H:%M}"

    if _atualizando.is_set():
        texto += " (atualizando agora…)"

    return texto
