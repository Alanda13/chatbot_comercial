"""
Confere se todo número de uma resposta existe nos dados — a trava contra
número inventado, valendo pra resposta final (não só pro histórico).

Em 06/10/2026, numa análise ("as filiais com NPS acima de 90 dão mais
desconto?"), o código executado pela IA calculava "sem Parnaíba: 2,70%",
mas o texto saía com 2,75%, 2,23% ou 3,17%. A conferência aceita um número
do texto quando ele é um ARREDONDAMENTO ou ABREVIAÇÃO de algum valor que
existe nos dados (resultado do sistema, saída do código, pergunta):
"3,14%" ← 3,1387; "R$ 8,57 mi" ← 8.566.753,98. O resto é inventado.
"""
import re

# Número em português: "8.566.753,98", "3,14", "2026".
_NUMERO_PT = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?")
# Número na saída do Python: "8,566,753.98", "3.14", "0.26".
_NUMERO_EN = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
_ESCALA = re.compile(r"\s*(mi\b|milh|mil\b|bi\b|bilh)", re.IGNORECASE)
_MULTIPLICADOR = {"mi": 1e6, "milh": 1e6, "mil": 1e3, "bi": 1e9, "bilh": 1e9}


def _numeros_do_texto(texto: str) -> list[tuple[float, int, float, str]]:
    """(valor, casas decimais escritas, multiplicador de "mi"/"mil", texto)."""
    numeros = []

    for achado in _NUMERO_PT.finditer(texto):
        bruto = achado.group()
        casas = len(bruto.split(",")[1]) if "," in bruto else 0
        valor = float(bruto.replace(".", "").replace(",", "."))
        escala = _ESCALA.match(texto, achado.end())
        multiplicador = _MULTIPLICADOR[escala.group(1).lower()] if escala else 1.0
        numeros.append((valor, casas, multiplicador, bruto))

    return numeros


def _valores(dado, saida: set[float]) -> set[float]:
    """Todos os números dentro de um resultado (dict/list/str/número)."""
    if isinstance(dado, bool) or dado is None:
        return saida
    if isinstance(dado, (int, float)):
        saida.add(float(dado))
    elif isinstance(dado, str):
        saida |= {valor for valor, *_ in _numeros_do_texto(dado)}
    elif isinstance(dado, dict):
        for item in dado.values():
            _valores(item, saida)
    elif isinstance(dado, (list, tuple)):
        for item in dado:
            _valores(item, saida)
    return saida


def valores_permitidos(*fontes, saidas_de_codigo: list[str] = ()) -> set[float]:
    permitidos: set[float] = set()

    for fonte in fontes:
        _valores(fonte, permitidos)

    for saida in saidas_de_codigo:
        permitidos |= {
            float(bruto.replace(",", "")) for bruto in _NUMERO_EN.findall(saida)
        }

    return permitidos


def numeros_inventados(texto: str, permitidos: set[float]) -> list[str]:
    """
    Números do texto que não são arredondamento/abreviação de nenhum valor
    permitido. Inteiros pequenos (até 99) são ignorados: numeração, "7
    filiais", "os 3 maiores".
    """
    inventados = []

    for valor, casas, multiplicador, bruto in _numeros_do_texto(texto):
        if casas == 0 and multiplicador == 1 and valor < 100:
            continue

        tolerancia = 0.5 * 10 ** -casas
        if not any(
            abs(permitido / multiplicador - valor) <= tolerancia + 1e-9
            for permitido in permitidos
        ):
            inventados.append(bruto)

    return inventados
