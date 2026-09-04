from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import Restaurant

# Sementes de categorias do plano (secção 6).
SEED_CATEGORIES = ["Bebidas", "Mercearia", "Frescos", "Limpeza", "Embalagem"]


@receiver(post_save, sender=Restaurant)
def seed_categories(sender, instance, created, **kwargs):
    if not created:
        return
    from .models import Category

    Category.objects.bulk_create(
        [Category(restaurant=instance, name=name) for name in SEED_CATEGORIES]
    )
