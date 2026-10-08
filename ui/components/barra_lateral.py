"""
Barra lateral: "Experimente perguntar", um exemplo por indicador.
"""
import streamlit as st

from config.constants import PERGUNTAS_NORTEADORAS
from ui.formatacao import escapar_para_markdown


def mostrar_barra_lateral():
    with st.sidebar:
        with st.container(border=True, key="painel_perguntas"):
            st.markdown("#### 💡 Experimente perguntar")
            st.caption("Um exemplo por indicador. Clique para ver no chat.")

            for indice, item in enumerate(PERGUNTAS_NORTEADORAS):
                st.markdown(
                    f'<div class="rotulo-indicador">{item["categoria"]}</div>',
                    unsafe_allow_html=True,
                )

                if st.button(
                    item["pergunta"],
                    key=f"norteadora_{indice}",
                    use_container_width=True,
                ):
                    if item["resposta"] is None:
                        st.session_state.pergunta_sugerida = item["pergunta"]
                    else:
                        st.session_state.mensagens.append(
                            {"papel": "user", "conteudo": item["pergunta"]}
                        )
                        st.session_state.mensagens.append(
                            {
                                "papel": "assistant",
                                "conteudo": item["resposta"],
                                "dados_tabela": None,
                            }
                        )

                resposta_previa = item["resposta"] or "Busca o dado atualizado na hora do clique."
                st.caption(
                    escapar_para_markdown(resposta_previa),
                    unsafe_allow_html=True,
                )

                if indice < len(PERGUNTAS_NORTEADORAS) - 1:
                    st.markdown(
                        '<hr class="separador-indicador">', unsafe_allow_html=True
                    )
