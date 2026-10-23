"""
Atualiza os CSVs do Oracle em segundo plano — quem pergunta nunca espera.

- ao abrir o chatbot: atualização COMPLETA (desde 2020), em segundo plano
  — enquanto isso, as perguntas usam os CSVs que já existem;
- de hora em hora, das 7h às 19h: PARCIAL (só o mês atual e o anterior);
- o 1º ciclo de cada dia (a partir das 7h) é COMPLETO: pega devoluções e
  cancelamentos em meses antigos;
- à noite não roda nada. Se o Oracle falhar, fica valendo o CSV anterior.

Roda num PROGRAMA SEPARADO (`python -m core.services.atualizador_service`):
no mesmo programa do chatbot, a atualização (milhões de linhas) ocuparia o
processador e atrasaria as perguntas. `iniciar()` (chamado pelo app.py) só
abre esse programa:

- um atualizador por vez: cada um segura `data/atualizador.trava`; um
  novo (o Streamlit recarregou o código) espera o antigo sair;
- o atualizador para quando o chatbot fecha: ele lê a entrada (stdin)
  que o chatbot mantém aberta e sai quando ela fecha;
- a completa ao abrir só roda se ainda não rodou hoje
  (`data/ultima_completa.txt`); senão, ao abrir faz a parcial.
"""
import os
import subprocess
import sys
import threading
import time
from datetime import date, datetime

from core.repositories.arquivos_repository import com_tentativas, marcar_atualizador_ativo
from core.repositories.faturamento_repository import RAIZ_PROJETO
from core.logger import obter_logger

logger = obter_logger(__name__)

ARQUIVO_TRAVA = RAIZ_PROJETO / "data" / "atualizador.trava"
ARQUIVO_ULTIMA_COMPLETA = RAIZ_PROJETO / "data" / "ultima_completa.txt"
# Existe enquanto uma atualização roda: o chatbot mostra "(atualizando
# agora…)". Mais velho que isso é sobra de um atualizador que caiu.
ARQUIVO_ATUALIZANDO = RAIZ_PROJETO / "data" / "atualizando.agora"
_SEGUNDOS_MAXIMOS_ATUALIZANDO = 30 * 60

HORA_INICIO = 7
HORA_FIM = 19
_SEGUNDOS_ENTRE_PARCIAIS = 3600
_SEGUNDOS_ENTRE_VERIFICACOES = 60

_trava_inicio = threading.Lock()
_iniciado = False
_processo = None  # o atualizador aberto por este chatbot (mantém o stdin aberto)


def _bases():
    # Import aqui dentro: os módulos de dados importam core.repositories.arquivos_repository,
    # e o atualizador só precisa deles quando roda.
    from core.repositories import cliente_produto_repository
    from core.repositories import cliente_repository as cliente_data
    from core.repositories import faturamento_repository as faturamento_data
    from core.repositories import faturamento_diario_repository as faturamento_diario_data
    from core.repositories import produto_repository as produto_data
    from core.repositories import rca_repository
    from core.repositories import situacao_cliente_repository
    from core.repositories import venda_repository

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
        ("desconto por venda", venda_repository.atualizar,
         [venda_repository.ARQUIVO_DESCONTO_VENDA, venda_repository.ARQUIVO_DEVOLUCAO_CLIENTE]),
        ("mix de produtos dos clientes", cliente_produto_repository.atualizar,
         [cliente_produto_repository.ARQUIVO_CLIENTE_PRODUTO]),
        ("compras dos clientes", situacao_cliente_repository.atualizar,
         [situacao_cliente_repository.ARQUIVO_COMPRAS_CLIENTES]),
        ("cadastro de RCAs", rca_repository.atualizar, [rca_repository.ARQUIVO_RCAS]),
    ]


def rodar_atualizacao(completa: bool) -> None:
    """Atualiza todas as bases; a falha de uma não impede as outras."""
    ARQUIVO_ATUALIZANDO.parent.mkdir(parents=True, exist_ok=True)
    ARQUIVO_ATUALIZANDO.touch()
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
        ARQUIVO_ATUALIZANDO.unlink(missing_ok=True)


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


def estado_inicial(hoje: date, dia_da_ultima_completa: date | None):
    """
    (ultima_completa, ultima_parcial) ao abrir: completa já feita hoje, só
    a parcial; senão, a completa, a qualquer hora.
    """
    if dia_da_ultima_completa == hoje:
        return hoje, None
    return None, time.time()


def _ler_ultima_completa() -> date | None:
    try:
        return date.fromisoformat(ARQUIVO_ULTIMA_COMPLETA.read_text().strip())
    except (OSError, ValueError):
        return None


def _laco() -> None:
    ultima_completa, ultima_parcial = estado_inicial(date.today(), _ler_ultima_completa())

    while True:
        agora = datetime.now()
        acao = proxima_acao(agora, ultima_completa, ultima_parcial)

        if acao == "completa":
            rodar_atualizacao(completa=True)
            ultima_completa = agora.date()
            ultima_parcial = time.time()
            ARQUIVO_ULTIMA_COMPLETA.write_text(ultima_completa.isoformat())
        elif acao == "parcial":
            rodar_atualizacao(completa=False)
            ultima_parcial = time.time()

        time.sleep(_SEGUNDOS_ENTRE_VERIFICACOES)


def iniciar() -> None:
    """Abre o atualizador como programa separado (uma vez por chatbot)."""
    global _iniciado, _processo

    with _trava_inicio:
        if _iniciado:
            return
        _iniciado = True

    marcar_atualizador_ativo()
    _processo = subprocess.Popen(
        [sys.executable, "-m", "core.services.atualizador_service"],
        cwd=RAIZ_PROJETO,
        stdin=subprocess.PIPE,
    )


def _sair_quando_o_chatbot_fechar() -> None:
    sys.stdin.read()  # só volta quando o chatbot fecha a entrada
    logger.info("Chatbot fechado — atualizador encerrado.")
    os._exit(0)


def _travar(arquivo):
    """Tenta segurar a trava (sem esperar). True se conseguiu."""
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(arquivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _rodar_como_programa() -> None:
    threading.Thread(target=_sair_quando_o_chatbot_fechar, daemon=True).start()

    ARQUIVO_TRAVA.parent.mkdir(parents=True, exist_ok=True)
    trava = open(ARQUIVO_TRAVA, "a+")  # fica aberta (e travada) até o programa sair

    if not _travar(trava):
        logger.info("Outro atualizador rodando — esperando ele sair.")
        while not _travar(trava):
            time.sleep(5)

    marcar_atualizador_ativo()
    _laco()


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

    try:
        idade = time.time() - ARQUIVO_ATUALIZANDO.stat().st_mtime
    except OSError:
        idade = None

    if idade is not None and idade < _SEGUNDOS_MAXIMOS_ATUALIZANDO:
        texto += " (atualizando agora…)"

    return texto


if __name__ == "__main__":
    _rodar_como_programa()
