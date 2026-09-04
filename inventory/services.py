"""
Único ponto de escrita de Item.current_stock (invariante 1 do plano).
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Item, StockMovement

_NEGATIVOS = {StockMovement.Type.SAIDA, StockMovement.Type.AJUSTE_NEG}


def register_movement(*, item, movement_type, quantity, user, occurred_at=None, reason="", reference=""):
    """
    Regista um movimento e atualiza o stock do artigo na mesma transação,
    com lock sobre o artigo. Levanta ValidationError com mensagens em
    português simples (secção 9) quando o movimento não é válido.
    """
    if movement_type not in StockMovement.Type.values:
        raise ValidationError("Tipo de movimento desconhecido.")
    quantity = Decimal(quantity)
    if quantity <= 0:
        raise ValidationError("A quantidade tem de ser maior que zero.")

    with transaction.atomic():
        locked = Item.objects.select_for_update().get(pk=item.pk)
        delta = -quantity if movement_type in _NEGATIVOS else quantity
        new_stock = locked.current_stock + delta
        if new_stock < 0:
            raise ValidationError(
                f"Este movimento deixaria o stock em {new_stock} {locked.unit}. "
                f"O stock registado agora é {locked.current_stock} {locked.unit}. "
                "Se a contagem física for outra, registe primeiro um ajuste."
            )
        movement = StockMovement.objects.create(
            item=locked,
            movement_type=movement_type,
            quantity=quantity,
            occurred_at=occurred_at or timezone.now(),
            created_by=user,
            reason=reason,
            reference=reference,
        )
        locked.current_stock = new_stock
        locked.save(update_fields=["current_stock", "updated_at"])
    return movement
