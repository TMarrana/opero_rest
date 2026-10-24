from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Restaurant

# Áreas de origem de um restaurante (Fase 5).
SEED_WORK_AREAS = ["Cozinha", "Sala", "Bar"]


@receiver(post_save, sender=Restaurant)
def seed_work_areas(sender, instance, created, **kwargs):
    if not created:
        return
    from .models import WorkArea

    WorkArea.objects.bulk_create([WorkArea(restaurant=instance, name=name) for name in SEED_WORK_AREAS])
