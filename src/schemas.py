from typing import Any, Literal

from pydantic import BaseModel, Field

class SolicitacaoFerramenta(BaseModel):
    """
    Representa a resposta estruturada da IA para o Python.
    """
    acao: Literal[
        "executar_ferramenta",
        "pedir_esclarecimento",
        "fora_do_escopo",
    ]
    ferramenta: str | None = None
    argumentos: dict[str, Any] = Field(
        default_factory=dict
    )
    mensagem: str | None = None
   