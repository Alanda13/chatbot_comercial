"""
Força uma atualização manual do faturamento diário, direto do Oracle
(`dados/faturamento_diario.csv`).

Normalmente não é preciso rodar isso: `src.faturamento_diario_data` já
atualiza esse arquivo sozinho (a cada 1 hora, quando alguém pergunta
algo de faturamento diário pelo chatbot — ver docstring de
`src/faturamento_diario_data.py`). Esse script serve só pra forçar uma
atualização na hora, ou gerar um arquivo de teste separado.

Uso:
    python -m scripts.atualizar_faturamento_diario_oracle
    python -m scripts.atualizar_faturamento_diario_oracle --desde 2024-01-01 --saida dados/teste.csv
"""
import argparse
from datetime import date
from pathlib import Path

from src.faturamento_diario_data import ARQUIVO_FATURAMENTO_DIARIO, DESDE_PADRAO, gerar_tabela


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--desde", type=str, default=DESDE_PADRAO.isoformat(),
        help=f"Primeira data a buscar, formato AAAA-MM-DD (padrão: {DESDE_PADRAO.isoformat()}).",
    )
    parser.add_argument(
        "--saida", type=Path, default=ARQUIVO_FATURAMENTO_DIARIO,
        help="Arquivo CSV a gravar (padrão: sobrescreve o CSV atual).",
    )
    argumentos = parser.parse_args()

    ano, mes, dia = (int(parte) for parte in argumentos.desde.split("-"))
    tabela = gerar_tabela(date(ano, mes, dia))

    argumentos.saida.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_csv(
        argumentos.saida, sep=";", encoding="latin1", decimal=",", index=False,
    )
    print(f"{len(tabela)} linhas gravadas em {argumentos.saida}")


if __name__ == "__main__":
    main()
