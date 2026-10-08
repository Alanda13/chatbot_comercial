"""
Funções comuns aos CSVs gerados do Oracle (faturamento mensal, diário,
forma de pagamento, cliente).

Os CSVs são atualizados em segundo plano por `core/services/atualizador_service.py` — quem
pergunta nunca espera o Oracle. Aqui ficam as peças que os módulos de
dados compartilham:

- `ler_csv` / `gravar_csv`: a gravação escreve num arquivo temporário e
  troca pelo definitivo de uma vez (`os.replace`), com uma trava em
  comum com a leitura — ninguém lê um CSV pela metade nem enquanto ele é
  trocado (no Windows, trocar um arquivo aberto dá erro).
- `inicio_da_janela_parcial`: a atualização de hora em hora busca só o
  mês atual e o anterior (o resto do histórico vem do CSV que já existe).
- `garantir`: chamado na leitura. Arquivo que não existe é gerado na
  hora (a única espera). Sem o atualizador rodando (scripts, testes), um
  arquivo com mais de 1 hora é atualizado na hora, como antes.
"""
import os
import threading
import time
from datetime import date
from pathlib import Path
from typing import Callable

import pandas as pd

from core.logger import obter_logger

logger = obter_logger(__name__)

SEGUNDOS_VALIDADE = 3600
_TENTATIVAS_ORACLE = 3
_SEGUNDOS_ENTRE_TENTATIVAS = 5
_OPCOES_CSV = {"sep": ";", "encoding": "latin1", "decimal": ","}

_trava = threading.RLock()
_atualizador_ativo = threading.Event()


def marcar_atualizador_ativo() -> None:
    _atualizador_ativo.set()


def ler_csv(arquivo: Path, **opcoes) -> pd.DataFrame:
    with _trava:
        return pd.read_csv(arquivo, **_OPCOES_CSV, **opcoes)


def gravar_csv(tabela: pd.DataFrame, arquivo: Path) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    temporario = arquivo.with_name(arquivo.name + ".novo")
    tabela.to_csv(temporario, **_OPCOES_CSV, errors="replace", index=False)

    for tentativa in range(10):
        try:
            with _trava:
                os.replace(temporario, arquivo)
            return
        except PermissionError:
            # Outro programa (ex: o CSV aberto no Excel) segurando o arquivo.
            if tentativa == 9:
                raise
            time.sleep(1)


def inicio_da_janela_parcial(hoje: date | None = None) -> date:
    """1º dia do mês anterior: a parcial busca esse mês e o atual."""
    hoje = hoje or date.today()
    ano, mes = (hoje.year, hoje.month - 1) if hoje.month > 1 else (hoje.year - 1, 12)
    return date(ano, mes, 1)


def antes_da_janela_mensal(dados: pd.DataFrame, desde: date) -> pd.DataFrame:
    """Linhas (ANO/MES) que a parcial não busca de novo — ficam do CSV antigo."""
    return dados[dados["ANO"] * 100 + dados["MES"] < desde.year * 100 + desde.month]


def com_tentativas(descricao: str, funcao: Callable[[], None]) -> None:
    ultimo_erro = None

    for tentativa in range(1, _TENTATIVAS_ORACLE + 1):
        try:
            funcao()
            return
        except Exception as erro:
            ultimo_erro = erro
            logger.warning(
                f"Falha ao atualizar {descricao} do Oracle "
                f"(tentativa {tentativa}/{_TENTATIVAS_ORACLE}): {erro}"
            )
            if tentativa < _TENTATIVAS_ORACLE:
                time.sleep(_SEGUNDOS_ENTRE_TENTATIVAS)

    raise ultimo_erro


def garantir(
    arquivos: list[Path], atualizar: Callable[[bool], None], descricao: str
) -> None:
    if not all(arquivo.exists() for arquivo in arquivos):
        com_tentativas(descricao, lambda: atualizar(True))
        return

    if _atualizador_ativo.is_set():
        return

    idade = time.time() - min(arquivo.stat().st_mtime for arquivo in arquivos)

    if idade >= SEGUNDOS_VALIDADE:
        try:
            com_tentativas(descricao, lambda: atualizar(False))
        except Exception:
            logger.warning(
                f"Não foi possível atualizar {descricao} — seguindo com o "
                "CSV existente (pode estar desatualizado)."
            )
