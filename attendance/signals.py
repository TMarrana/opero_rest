from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import Restaurant

# Tipos de pausa de origem (Fase 5): (nome, paga).
SEED_BREAK_TYPES = [("Refeição", False), ("Pausa curta", True)]


@receiver(post_save, sender=Restaurant)
def seed_break_types(sender, instance, created, **kwargs):
    if not created:
        return
    from .models import BreakType

    BreakType.objects.bulk_create(
        [BreakType(restaurant=instance, name=name, paid=paid) for name, paid in SEED_BREAK_TYPES]
    )
