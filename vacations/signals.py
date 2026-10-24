from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import Restaurant

# Tipos de ausência de origem (Fase 5):
# (nome, desconta saldo, precisa de aprovação, meio dia, cor)
SEED_ABSENCE_TYPES = [
    ("Férias", True, True, True, "carvao"),
    ("Falta justificada", False, True, False, "ardosia"),
    ("Baixa médica", False, False, False, "ardosia"),
    ("Licença parental", False, False, False, "aco"),
    ("Formação", False, True, True, "aco"),
]


@receiver(post_save, sender=Restaurant)
def seed_absence_types(sender, instance, created, **kwargs):
    if not created:
        return
    from .models import AbsenceType

    AbsenceType.objects.bulk_create(
        [
            AbsenceType(
                restaurant=instance, name=n, deducts_balance=d, requires_approval=a, half_days=h, color=c
            )
            for n, d, a, h, c in SEED_ABSENCE_TYPES
        ]
    )
