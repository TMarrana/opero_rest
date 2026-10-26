"""
Único ponto de escrita de Item.current_stock (invariante 1 do plano).
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Item, StockMovement, StockTransfer

_NEGATIVOS = {StockMovement.Type.SAIDA, StockMovement.Type.AJUSTE_NEG}


def register_movement(
    *,
    item,
    movement_type,
    quantity,
    user,
    occurred_at=None,
    reason="",
    reference="",
    origin=StockMovement.Origin.MANUAL,
    transfer=None,
):
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
            origin=origin,
            transfer=transfer,
        )
        locked.current_stock = new_stock
        locked.save(update_fields=["current_stock", "updated_at"])
    return movement


def transfer_stock(*, source_item, destination_item, quantity, user, note=""):
    """Leva stock de uma casa para outra do mesmo grupo (Fase 9): a saída e
    a entrada fazem-se na mesma transação, ou não se faz nenhuma. Sem
    conversão de unidades (docx), por isso os dois artigos têm de ter a
    mesma unidade."""
    quantity = Decimal(quantity)
    if quantity <= 0:
        raise ValidationError("A quantidade tem de ser maior que zero.")
    origem, destino = source_item.restaurant, destination_item.restaurant
    if origem.pk == destino.pk:
        raise ValidationError("A casa de destino tem de ser outra.")
    if origem.organization_id != destino.organization_id:
        raise ValidationError("Só se transfere entre casas do mesmo grupo.")
    if source_item.unit != destination_item.unit:
        raise ValidationError(
            f"O artigo de destino está em {destination_item.get_unit_display()} e o de origem em "
            f"{source_item.get_unit_display()}. Escolha um artigo com a mesma unidade."
        )
    with transaction.atomic():
        agora = timezone.now()
        transferencia = StockTransfer.objects.create(
            source_item=source_item,
            destination_item=destination_item,
            quantity=quantity,
            occurred_at=agora,
            created_by=user,
            note=note,
        )
        comum = {
            "quantity": quantity,
            "user": user,
            "occurred_at": agora,
            "reference": f"TRF-{transferencia.pk}",
            "origin": StockMovement.Origin.TRANSFERENCIA,
            "transfer": transferencia,
        }
        register_movement(
            item=source_item, movement_type=StockMovement.Type.SAIDA, reason=f"Para {destino}", **comum
        )
        register_movement(
            item=destination_item, movement_type=StockMovement.Type.ENTRADA, reason=f"De {origem}", **comum
        )
    return transferencia
