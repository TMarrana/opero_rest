"""
Uma linha da ficha liga-se ao artigo pelo nome. Quando um artigo muda de
nome e nenhuma outra casa do grupo tem um artigo com o nome antigo, as
fichas passam a usar o nome novo, para não se desligarem.
"""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from inventory.models import Item


@receiver(pre_save, sender=Item)
def guardar_nome_antigo(sender, instance, update_fields=None, **kwargs):
    if instance.pk is None or (update_fields is not None and "name" not in update_fields):
        return
    instance._nome_antigo = Item.objects.filter(pk=instance.pk).values_list("name", flat=True).first()


@receiver(post_save, sender=Item)
def acompanhar_nome(sender, instance, created, **kwargs):
    from .models import RecipeLine

    antigo = getattr(instance, "_nome_antigo", None)
    if created or not antigo or antigo == instance.name:
        return
    grupo = instance.restaurant.organization_id
    if Item.objects.filter(restaurant__organization_id=grupo, name__iexact=antigo).exclude(pk=instance.pk).exists():
        return
    RecipeLine.objects.filter(
        version__recipe__organization_id=grupo, item_name__iexact=antigo, unit=instance.unit
    ).update(item_name=instance.name)
