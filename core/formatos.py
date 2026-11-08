"""Números para os ecrãs, à portuguesa: espaço nos milhares, vírgula decimal
e figuras tabulares (secção 4). Os templates usam-nos como filtros:
`euros` e `numero` pela biblioteca `vendas`, `quantidade` e `unidade` pela
`interface`."""
from decimal import ROUND_HALF_UP, Decimal

# Como as unidades dos artigos se escrevem nos ecrãs (o código fica na base de dados).
UNIDADES = {"UN": "un", "KG": "kg", "L": "L", "CX": "cx", "EMB": "emb"}


def _milhares(valor, casas):
    texto = f"{abs(valor):,.{casas}f}".replace(",", " ").replace(".", ",")
    return ("-" if valor < 0 else "") + texto


def euros(valor):
    """1 234,56 € em figuras mono: espaço nos milhares e vírgula decimal."""
    if valor is None:
        return "—"
    return _milhares(Decimal(valor), 2) + " €"


def numero(valor, casas=0):
    """Um número inteiro, ou com `casas` casas decimais (2 por omissão) quando as tem."""
    if valor is None:
        return "—"
    valor = Decimal(valor)
    if valor == valor.to_integral_value():
        return _milhares(valor, 0)
    return _milhares(valor, int(casas) or 2)


def preco(valor):
    """Preço unitário: duas casas, ou até quatro quando as tem (0,8550 fica 0,855)."""
    if valor is None:
        return "—"
    valor = Decimal(valor)
    casas = max(2, min(4, -valor.normalize().as_tuple().exponent))
    return _milhares(valor, casas) + " €"


def unidade(codigo):
    """A unidade de um artigo como se escreve: «KG» → «kg»."""
    return UNIDADES.get(codigo, codigo)


def quantidade(valor, unidade_codigo=""):
    """Uma quantidade de stock: arredondada às 3 casas decimais, sem zeros à
    direita, e a unidade em minúsculas (4 kg, 0,22 L, 1 250,5 kg). Sem valor, «—»."""
    if valor is None or valor == "":
        return "—"
    # str() para um float dar 0,22 e não 0,2200000000000000011…; o «+ 0» tira o sinal a -0,000.
    valor = Decimal(str(valor)).quantize(Decimal("0.001"), ROUND_HALF_UP) + 0
    casas = max(0, -valor.normalize().as_tuple().exponent)
    texto = _milhares(valor, casas)
    rotulo = unidade(unidade_codigo)
    return f"{texto} {rotulo}" if rotulo else texto
