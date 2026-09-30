"""
Força uma atualização manual do faturamento mensal, direto do Oracle
(`dados/faturamento_mensal.csv`).

Normalmente não é preciso rodar isso: `src.faturamento_data` já
atualiza esse arquivo sozinho (a cada 1 hora, quando alguém pergunta
algo de faturamento pelo chatbot — ver docstring de
`src/faturamento_data.py`). Esse script serve só pra forçar uma
atualização na hora, ou gerar um arquivo de teste separado.

Uso:
    python -m scripts.atualizar_faturamento_oracle
    python -m scripts.atualizar_faturamento_oracle --ano-inicio 2022 --saida dados/teste.csv
"""
import argparse
from pathlib import Path

from src.faturamento_data import ANO_INICIO_PADRAO, ARQUIVO_FATURAMENTO_MENSAL, gerar_tabela


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ano-inicio", type=int, default=ANO_INICIO_PADRAO,
        help=f"Primeiro ano a buscar (padrão: {ANO_INICIO_PADRAO}).",
    )
    parser.add_argument(
        "--saida", type=Path, default=ARQUIVO_FATURAMENTO_MENSAL,
        help="Arquivo CSV a gravar (padrão: sobrescreve o CSV atual).",
    )
    argumentos = parser.parse_args()

    tabela = gerar_tabela(argumentos.ano_inicio)

    argumentos.saida.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_csv(
        argumentos.saida, sep=";", encoding="latin1", decimal=",", index=False,
    )
    print(f"{len(tabela)} linhas gravadas em {argumentos.saida}")


if __name__ == "__main__":
    main()
