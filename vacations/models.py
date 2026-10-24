from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class AbsenceType(TimeStampedModel):
    """Tipo de ausência (Fase 5): férias, falta justificada, baixa,
    licença parental, formação. Um tipo que não exige aprovação fica
    aprovado logo que é pedido (R-051). Arquiva-se em vez de se apagar,
    porque os pedidos já feitos apontam para ele."""

    class Color(models.TextChoices):
        # Tons neutros: a paleta tem uma só cor quente e uma de estado
        # (secção 4), e as ausências não podem competir com elas.
        CARVAO = "carvao", "Carvão"
        ARDOSIA = "ardosia", "Ardósia"
        ACO = "aco", "Aço"

    restaurant = models.ForeignKey(
        "core.Restaurant", verbose_name="restaurante", on_delete=models.CASCADE, related_name="absence_types"
    )
    name = models.CharField("nome", max_length=60)
    color = models.CharField("cor", max_length=10, choices=Color.choices, default=Color.ARDOSIA)
    deducts_balance = models.BooleanField("desconta do saldo de férias", default=False)
    requires_approval = models.BooleanField("precisa de aprovação", default=True)
    half_days = models.BooleanField("permite meio dia", default=False)
    archived_at = models.DateTimeField("arquivado em", null=True, blank=True)

    class Meta:
        verbose_name = "tipo de ausência"
        verbose_name_plural = "tipos de ausência"
        ordering = ["name"]

    def __str__(self):
        return self.name


class VacationRequest(TimeStampedModel):
    """Pedido de ausência (férias ou outro tipo). Invariante 6: aprovados
    não se apagam; a sobreposição com aprovados do mesmo trabalhador é
    assinalada."""

    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        APROVADO = "APROVADO", "Aprovado"
        RECUSADO = "RECUSADO", "Recusado"
        CANCELADO = "CANCELADO", "Cancelado"

    worker = models.ForeignKey(
        "workers.Worker", verbose_name="trabalhador", on_delete=models.CASCADE, related_name="vacation_requests"
    )
    absence_type = models.ForeignKey(
        AbsenceType, verbose_name="tipo", on_delete=models.PROTECT, related_name="requests"
    )
    start_date = models.DateField("início")
    end_date = models.DateField("fim")
    half_day = models.BooleanField("meio dia", default=False)
    days_taken = models.DecimalField("dias", max_digits=5, decimal_places=1, default=0)
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
    cancelled_at = models.DateTimeField("cancelado em", null=True, blank=True)

    class Meta:
        verbose_name = "pedido de ausência"
        verbose_name_plural = "pedidos de ausência"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="ferias_fim_depois_do_inicio",
            ),
            models.CheckConstraint(
                condition=models.Q(half_day=False) | models.Q(end_date=models.F("start_date")),
                name="meio_dia_so_num_dia",
            ),
        ]

    def __str__(self):
        return f"{self.worker}: {self.start_date} a {self.end_date} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        # Sem tipo, o pedido é de férias: o tipo que desconta do saldo.
        if self.absence_type_id is None:
            self.absence_type = (
                AbsenceType.objects.filter(restaurant_id=self.worker.restaurant_id, deducts_balance=True)
                .order_by("archived_at", "pk")
                .first()
            )
        super().save(*args, **kwargs)

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


class Allowance(TimeStampedModel):
    """Saldo anual de férias de um trabalhador (Fase 5). Os dias
    transitados do ano anterior gastam-se primeiro e caducam na data
    definida (R-066). Sem registo, vale o valor por defeito da
    configuração (VACATION_DEFAULT_DAYS)."""

    worker = models.ForeignKey(
        "workers.Worker", verbose_name="trabalhador", on_delete=models.CASCADE, related_name="allowances"
    )
    year = models.PositiveSmallIntegerField("ano")
    days = models.DecimalField("dias do ano", max_digits=5, decimal_places=1)
    carried_over = models.DecimalField("dias transitados", max_digits=5, decimal_places=1, default=0)
    carry_over_expires_on = models.DateField("transitados caducam em", null=True, blank=True)

    class Meta:
        verbose_name = "saldo de férias"
        verbose_name_plural = "saldos de férias"
        ordering = ["-year"]
        constraints = [models.UniqueConstraint(fields=["worker", "year"], name="um_saldo_por_ano")]

    def __str__(self):
        return f"{self.worker} · {self.year}"


class Holiday(TimeStampedModel):
    """Feriado municipal ou do restaurante. Os nacionais calculam-se em
    `vacations.holidays`, e não se guardam aqui."""

    restaurant = models.ForeignKey(
        "core.Restaurant", verbose_name="restaurante", on_delete=models.CASCADE, related_name="holidays"
    )
    date = models.DateField("data")
    name = models.CharField("nome", max_length=80)
    half_day = models.BooleanField("meio dia", default=False)

    class Meta:
        verbose_name = "feriado"
        verbose_name_plural = "feriados"
        ordering = ["date"]
        constraints = [models.UniqueConstraint(fields=["restaurant", "date"], name="um_feriado_por_dia")]

    def __str__(self):
        return f"{self.name} ({self.date:%d/%m/%Y})"


class BlockedPeriod(TimeStampedModel):
    """Período em que não se aceitam pedidos de ausência (R-060), por
    exemplo a época alta. Sem tipos escolhidos, bloqueia todos."""

    restaurant = models.ForeignKey(
        "core.Restaurant", verbose_name="restaurante", on_delete=models.CASCADE, related_name="blocked_periods"
    )
    name = models.CharField("motivo", max_length=80)
    start = models.DateField("início")
    end = models.DateField("fim")
    absence_types = models.ManyToManyField(
        AbsenceType, verbose_name="tipos bloqueados", blank=True, related_name="blocked_periods"
    )
    exempt_workers = models.ManyToManyField(
        "workers.Worker", verbose_name="trabalhadores isentos", blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "período bloqueado"
        verbose_name_plural = "períodos bloqueados"
        ordering = ["start"]
        constraints = [
            models.CheckConstraint(condition=models.Q(end__gte=models.F("start")), name="bloqueio_fim_depois_do_inicio"),
        ]

    def __str__(self):
        return f"{self.name}: {self.start:%d/%m} a {self.end:%d/%m/%Y}"
