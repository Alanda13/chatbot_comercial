from pprint import pprint

from src.ai_service import interpretar_pergunta
from src.tool_manager import executar_ferramenta


def testar_chatbot():
    pergunta = "Qual é o NPS geral da empresa?"

    solicitacao = interpretar_pergunta(pergunta)

    print("\n=== DECISÃO DA IA ===\n")
    pprint(solicitacao.model_dump())

    if solicitacao.acao == "executar_ferramenta":
        if not solicitacao.ferramenta:
            raise ValueError(
                "A IA solicitou execução, mas não informou a ferramenta."
            )

        resultado = executar_ferramenta(
            solicitacao.ferramenta,
            solicitacao.argumentos,
        )

        print("\n=== RESULTADO DA CONSULTA ===\n")
        pprint(resultado)

    elif solicitacao.acao == "pedir_esclarecimento":
        print("\n=== ESCLARECIMENTO ===\n")
        print(solicitacao.mensagem)

    elif solicitacao.acao == "fora_do_escopo":
        print("\n=== FORA DO ESCOPO ===\n")
        print(
            solicitacao.mensagem
            or "Essa pergunta ainda não pode ser atendida pelo chatbot."
        )


if __name__ == "__main__":
    try:
        testar_chatbot()

    except Exception as error:
        print("\nOcorreu um erro durante o teste:")
        print(error)