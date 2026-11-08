from decimal import Decimal

from django import template

from core.formatos import euros, numero, preco

register = template.Library()

# Vivem em core.formatos; continuam aqui para os templates que fazem {% load vendas %}.
register.filter("euros", euros)
register.filter("numero", numero)
register.filter("preco", preco)


@register.filter
def variacao(valor):
    """+12 % ou -3 %, com o sinal sempre visivel."""
    if valor is None:
        return ""
    return f"{'+' if valor > 0 else ''}{valor} %".replace("-", "\u2212")


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
