from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class Worker(TimeStampedModel):
    """Pessoa que trabalha no restaurante. Pode ou não ter conta (User)."""

    restaurant = models.ForeignKey(
        "core.Restaurant", verbose_name="restaurante", on_delete=models.CASCADE, related_name="workers"
    )
    full_name = models.CharField("nome completo", max_length=150)
    contact = models.CharField("contacto", max_length=120, blank=True)
    job_title = models.CharField("função", max_length=80, blank=True)
    is_active = models.BooleanField("ativo", default=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="utilizador",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="worker",
    )
    start_date = models.DateField("data de início", null=True, blank=True)
    notes = models.TextField("notas", blank=True)

    class Meta:
        verbose_name = "trabalhador"
        verbose_name_plural = "trabalhadores"
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name

    @property
    def open_entry(self):
        return self.time_entries.filter(check_out__isnull=True).first()
