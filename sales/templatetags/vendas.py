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
