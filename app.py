import streamlit as st 

## CONFIGURAÇÃO DE PÁGINA
st.set_page_config(
    page_title="Chatbot Comercial Ferronorte",
    page_icon="💬",
    layout="wide"
)
st.title("💬 Chatbot Comercial Ferronorte")
st.write("Bem vindo! Faça uma pergunta sobre os indicadores comerciais.")

##  HISTÓRICO DE MENSAGENSSS
if "messages" not in st.session_state:
    st.session_state.messages = []

#   PARA MOSTRAR O HISTÓRICO
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

#   CAIXA DE TEXTO
prompt = st.chat_input("Digite sua pergunta...")
if prompt:
    st.session_state.messages.append(
        {
            "role":"user",
            "content":prompt
        }  
    )
    with st.chat_message("user"):
         st.markdown(prompt)
 
    resposta = (
         "Ainda estou em desenvolvimento! \n\n"   #RESPOSTA TEMPORÁRIA -----> DEPOIS TROCARRRR!!!!!
         "Na próxima etapa vou consultar o banco de dados."
    )
    st.session_state.messages.append(
         {
              "role":"assistante",
              "content":resposta
         }
    )
    with st.chat_message("assistant"):
         st.markdown(resposta)
