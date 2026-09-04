from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class VacationRequest(TimeStampedModel):
    """Pedido de férias. Invariante 6: aprovados não se apagam; a
    sobreposição com aprovados do mesmo trabalhador é assinalada."""

    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        APROVADO = "APROVADO", "Aprovado"
        RECUSADO = "RECUSADO", "Recusado"
        CANCELADO = "CANCELADO", "Cancelado"

    worker = models.ForeignKey(
        "workers.Worker", verbose_name="trabalhador", on_delete=models.CASCADE, related_name="vacation_requests"
    )
    start_date = models.DateField("início")
    end_date = models.DateField("fim")
    status = models.CharField("estado", max_length=10, choices=Status.choices, default=Status.PENDENTE)
    request_note = models.CharField("observação do pedido", max_length=300, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="decidido por",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="vacation_decisions",
    )
    decided_at = models.DateTimeField("decidido em", null=True, blank=True)
    decision_note = models.CharField("observação da decisão", max_length=300, blank=True)

    class Meta:
        verbose_name = "pedido de férias"
        verbose_name_plural = "pedidos de férias"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="ferias_fim_depois_do_inicio",
            ),
        ]

    def __str__(self):
        return f"{self.worker}: {self.start_date} a {self.end_date} ({self.get_status_display()})"

    def overlapping_approved(self):
        """Pedidos aprovados do mesmo trabalhador que se sobrepõem a este."""
        return (
            VacationRequest.objects.filter(worker=self.worker, status=self.Status.APROVADO)
            .exclude(pk=self.pk)
            .filter(start_date__lte=self.end_date, end_date__gte=self.start_date)
        )

    @property
    def has_overlap(self):
        return self.overlapping_approved().exists()
