from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class TimeEntry(TimeStampedModel):
    """Turno de um trabalhador. Invariante 3: um só turno aberto por
    trabalhador, garantido por constraint parcial + validação no serviço."""

    worker = models.ForeignKey(
        "workers.Worker", verbose_name="trabalhador", on_delete=models.CASCADE, related_name="time_entries"
    )
    check_in = models.DateTimeField("entrada")
    check_out = models.DateTimeField("saída", null=True, blank=True)
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="corrigido por",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="attendance_corrections",
    )
    correction_reason = models.CharField("motivo da correção", max_length=200, blank=True)
    corrected_at = models.DateTimeField("corrigido em", null=True, blank=True)

    class Meta:
        verbose_name = "registo de ponto"
        verbose_name_plural = "registos de ponto"
        ordering = ["-check_in"]
        constraints = [
            models.UniqueConstraint(
                fields=["worker"],
                condition=models.Q(check_out__isnull=True),
                name="um_turno_aberto_por_trabalhador",
            ),
            models.CheckConstraint(
                condition=models.Q(check_out__isnull=True) | models.Q(check_out__gt=models.F("check_in")),
                name="saida_depois_da_entrada",
            ),
        ]

    def __str__(self):
        return f"{self.worker} @ {self.check_in:%Y-%m-%d %H:%M}"

    @property
    def is_open(self):
        return self.check_out is None

    @property
    def duration(self):
        if self.check_out is None:
            return None
        return self.check_out - self.check_in
