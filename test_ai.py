from src.chatbot import processar_pergunta

def testar_chatbot():
    pergunta = "Qual é o NPS de uma filial?"

    resposta = processar_pergunta(pergunta)

    print("\n=== PERGUNTA ===\n")
    print(pergunta)

    print("\n=== RESPOSTA DO CHATBOT ===\n")
    print(resposta)

if __name__ == "__main__":
    try:
        testar_chatbot()

    except KeyboardInterrupt:
        print("\nTeste interrompido pelo usuário.")

    except Exception as error:
        print("\nOcorreu um erro durante o teste:")
        print(error)