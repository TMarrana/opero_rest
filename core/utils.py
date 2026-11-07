from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

# Os meses em português escrevem-se com minúscula; o filtro `date:"F"` do
# Django dá-os com maiúscula («Vendas de Novembro»).
MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)


def nome_do_mes(dia):
    """«novembro» para qualquer dia de novembro."""
    return MESES[dia.month - 1]


def restaurant_scope(request, qs, field="restaurant"):
    """
    Restringe um queryset à casa ativa do pedido (Fase 9). Sem casa ativa
    não devolve nada: um utilizador sem acesso a nenhuma casa não vê os
    dados de todas.
    """
    if request.restaurant is None:
        return qs.none()
    return qs.filter(**{field: request.restaurant.pk})


def workers_scope(request, qs):
    """Os trabalhadores da casa ativa: os da casa principal e os que vêm de
    outra casa do grupo (Fase 9). Para a ficha, as férias e o fecho do mês,
    que são da casa principal, usar `restaurant_scope`."""
    if request.restaurant is None:
        return qs.none()
    return qs.in_restaurant(request.restaurant)


def parse_decimal(texto, campo="O valor"):
    """Um número escrito à portuguesa (vírgula decimal) ou com ponto. Vazio
    dá None."""
    texto = (texto or "").strip().replace(" ", "").replace(",", ".")
    if not texto:
        return None
    try:
        valor = Decimal(texto)
    except InvalidOperation as exc:
        raise ValidationError(f"{campo} «{texto}» não é um número.") from exc
    if valor < 0:
        raise ValidationError(f"{campo} não pode ser negativo.")
    return valor
