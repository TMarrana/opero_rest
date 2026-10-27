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
    com lock sobre o artigo. Só os movimentos de origem venda podem deixar o
    stock negativo. Levanta ValidationError com mensagens em
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
        # Uma venda que já aconteceu não se recusa (Fase 14, secção 12): o
        # stock fica negativo e o artigo assinalado até à contagem seguinte.
        if new_stock < 0 and origin != StockMovement.Origin.VENDA:
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


def register_count(*, item, counted, user, at=None):
    """Contagem física (Fase 14): a diferença para o stock registado entra
    como um ajuste de origem contagem, na mesma transação. Uma contagem
    igual ao registado fica guardada sem movimento: conta como contagem
    para o teórico contra real."""
    from .models import StockCount

    counted = Decimal(counted)
    if counted < 0:
        raise ValidationError("A quantidade contada não pode ser negativa.")
    at = at or timezone.now()
    if at > timezone.now():
        raise ValidationError("A contagem não pode ser no futuro.")
    with transaction.atomic():
        locked = Item.objects.select_for_update().get(pk=item.pk)
        esperado = locked.current_stock
        diferenca = counted - esperado
        movimento = None
        if diferenca:
            movimento = register_movement(
                item=locked,
                movement_type=StockMovement.Type.AJUSTE_POS if diferenca > 0 else StockMovement.Type.AJUSTE_NEG,
                quantity=abs(diferenca),
                user=user,
                occurred_at=at,
                reason="Contagem física",
                origin=StockMovement.Origin.CONTAGEM,
            )
        return StockCount.objects.create(
            item=locked,
            counted_at=at,
            counted_quantity=counted,
            expected_quantity=esperado,
            movement=movimento,
            created_by=user,
        )
