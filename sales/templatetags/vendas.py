from decimal import Decimal

from django import template

register = template.Library()


def _milhares(valor, casas):
    texto = f"{abs(valor):,.{casas}f}".replace(",", " ").replace(".", ",")
    return ("-" if valor < 0 else "") + texto


@register.filter
def euros(valor):
    """1 234,56 EUR em figuras mono: espaco nos milhares e virgula decimal."""
    if valor is None:
        return "—"
    return _milhares(Decimal(valor), 2) + " \u20ac"


@register.filter
def numero(valor, casas=0):
    """Quantidade sem zeros a mais: 12 ou 1,5."""
    if valor is None:
        return "—"
    valor = Decimal(valor)
    if valor == valor.to_integral_value():
        return _milhares(valor, 0)
    return _milhares(valor, int(casas) or 2)


@register.filter
def variacao(valor):
    """+12 % ou -3 %, com o sinal sempre visivel."""
    if valor is None:
        return ""
    return f"{'+' if valor > 0 else ''}{valor} %".replace("-", "\u2212")


@register.filter
def preco(valor):
    """Preco unitario: duas casas, ou ate quatro quando as tem (0,8550 fica 0,855)."""
    if valor is None:
        return "\u2014"
    valor = Decimal(valor)
    casas = max(2, min(4, -valor.normalize().as_tuple().exponent))
    return _milhares(valor, casas) + " \u20ac"


@register.filter
def campo(valor):
    """Valor para um campo de formulario: sem zeros a mais e com virgula (7,5)."""
    if valor is None or valor == "":
        return ""
    valor = Decimal(valor)
    if valor == valor.to_integral_value():
        return str(valor.quantize(Decimal(1)))
    return format(valor.normalize(), "f").replace(".", ",")


@register.filter
def campo_preco(valor):
    """Preco para um campo de formulario: pelo menos duas casas (0,90)."""
    if valor is None or valor == "":
        return ""
    valor = Decimal(valor)
    casas = max(2, min(4, -valor.normalize().as_tuple().exponent))
    return f"{valor:.{casas}f}".replace(".", ",")
