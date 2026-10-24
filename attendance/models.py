import datetime

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models import TimeStampedModel


def unresolved_limit():
    """Horas a partir das quais uma entrada sem saída fica por resolver
    (R-013). Valor provisório em configuração, a decidir com a AT."""
    return datetime.timedelta(hours=getattr(settings, "ATTENDANCE_UNRESOLVED_HOURS", 14))


class TimeEntryQuerySet(models.QuerySet):
    def unresolved(self, now=None):
        """Entradas sem saída que passaram do limite, ou que já foram
        postas de lado por uma entrada nova (`missing_exit`)."""
        now = now or timezone.now()
        return self.filter(check_out__isnull=True).filter(
            Q(missing_exit=True) | Q(check_in__lt=now - unresolved_limit())
        )

    def resolved(self, now=None):
        now = now or timezone.now()
        return self.exclude(pk__in=self.unresolved(now).values("pk"))


class TimeEntry(TimeStampedModel):
    """Turno de um trabalhador. Invariante 3: um só turno aberto por
    trabalhador, garantido por constraint parcial + validação no serviço.

    O dia de trabalho (`work_date`) é o dia da entrada, na hora local: um
    turno das 19h às 2h conta todo no dia em que começou (Fase 5)."""

    class Source(models.TextChoices):
        QUIOSQUE = "QUIOSQUE", "Tablet partilhado"
        TELEMOVEL = "TELEMOVEL", "Telemóvel"
        GERENTE = "GERENTE", "Gerente"

    worker = models.ForeignKey(
        "workers.Worker", verbose_name="trabalhador", on_delete=models.CASCADE, related_name="time_entries"
    )
    check_in = models.DateTimeField("entrada")
    check_out = models.DateTimeField("saída", null=True, blank=True)
    work_date = models.DateField("dia de trabalho", db_index=True)
    work_area = models.ForeignKey(
        "core.WorkArea",
        verbose_name="área",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="time_entries",
    )
    # Entrada sem saída posta de lado quando o trabalhador marcou uma
    # entrada nova. Fica por resolver até alguém indicar a saída; não conta
    # para os totais (invariante 9) e já não bloqueia o turno aberto único.
    missing_exit = models.BooleanField("saída em falta", default=False)
    # Vazio nos registos anteriores à Fase 5: a origem não ficou guardada.
    source = models.CharField("origem", max_length=10, choices=Source.choices, blank=True)
    # Cópia da última correção (EntryCorrection), mantida pelo serviço na
    # mesma transação. O histórico completo está nas correções.
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

    objects = TimeEntryQuerySet.as_manager()

    class Meta:
        verbose_name = "registo de ponto"
        verbose_name_plural = "registos de ponto"
        ordering = ["-check_in"]
        constraints = [
            models.UniqueConstraint(
                fields=["worker"],
                condition=models.Q(check_out__isnull=True, missing_exit=False),
                name="um_turno_aberto_por_trabalhador",
            ),
            models.CheckConstraint(
                condition=models.Q(check_out__isnull=True) | models.Q(check_out__gt=models.F("check_in")),
                name="saida_depois_da_entrada",
            ),
        ]

    def __str__(self):
        return f"{self.worker} @ {self.check_in:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        self.work_date = work_date_for(self.check_in)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "check_in" in update_fields:
            kwargs["update_fields"] = {*update_fields, "work_date"}
        super().save(*args, **kwargs)

    @property
    def is_open(self):
        return self.check_out is None

    def is_unresolved(self, now=None):
        if self.check_out is not None:
            return False
        now = now or timezone.now()
        return self.missing_exit or self.check_in < now - unresolved_limit()

    @property
    def duration(self):
        if self.check_out is None:
            return None
        return self.check_out - self.check_in

    @property
    def open_break(self):
        return self.breaks.filter(end__isnull=True).select_related("break_type").first()

    def unpaid_break_time(self, until=None):
        """Tempo em pausas não pagas. Uma pausa aberta conta até `until`
        (por defeito, agora)."""
        until = until or timezone.now()
        total = datetime.timedelta()
        for b in self.breaks.all():
            if b.break_type.paid:
                continue
            total += max((b.end or until) - b.start, datetime.timedelta())
        return total

    def worked(self, until=None):
        """Tempo trabalhado: da entrada à saída (ou a `until`, num turno
        aberto), sem as pausas não pagas. Um registo por resolver conta
        zero (invariante 9)."""
        until = until or timezone.now()
        if self.is_unresolved(now=until):
            return datetime.timedelta()
        fim = self.check_out or until
        return max(fim - self.check_in - self.unpaid_break_time(until=fim), datetime.timedelta())


def work_date_for(check_in):
    return timezone.localtime(check_in).date()


class BreakType(TimeStampedModel):
    """Tipo de pausa (Fase 5). As pausas não pagas não contam para os
    totais. Arquiva-se em vez de se apagar, porque as pausas já
    registadas apontam para ele (R-006)."""

    restaurant = models.ForeignKey(
        "core.Restaurant", verbose_name="restaurante", on_delete=models.CASCADE, related_name="break_types"
    )
    name = models.CharField("nome", max_length=60)
    paid = models.BooleanField("paga", default=False)
    archived_at = models.DateTimeField("arquivado em", null=True, blank=True)

    class Meta:
        verbose_name = "tipo de pausa"
        verbose_name_plural = "tipos de pausa"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Break(TimeStampedModel):
    """Pausa dentro de um turno. Só se inicia com a entrada marcada, e só
    pode haver uma pausa aberta de cada vez por turno (R-004)."""

    entry = models.ForeignKey(TimeEntry, verbose_name="registo", on_delete=models.CASCADE, related_name="breaks")
    break_type = models.ForeignKey(
        BreakType, verbose_name="tipo", on_delete=models.PROTECT, related_name="breaks"
    )
    start = models.DateTimeField("início")
    end = models.DateTimeField("fim", null=True, blank=True)

    class Meta:
        verbose_name = "pausa"
        verbose_name_plural = "pausas"
        ordering = ["start"]
        constraints = [
            models.UniqueConstraint(
                fields=["entry"],
                condition=models.Q(end__isnull=True),
                name="uma_pausa_aberta_por_registo",
            ),
            models.CheckConstraint(
                condition=models.Q(end__isnull=True) | models.Q(end__gt=models.F("start")),
                name="pausa_fim_depois_do_inicio",
            ),
        ]

    def __str__(self):
        return f"{self.break_type} @ {self.start:%Y-%m-%d %H:%M}"

    @property
    def duration(self):
        if self.end is None:
            return None
        return self.end - self.start


class EntryCorrection(models.Model):
    """Histórico de correções de um registo (invariante 7): cada correção
    guarda os valores antigos e os novos, com autor, motivo e data. Não
    se edita nem se apaga."""

    class Kind(models.TextChoices):
        CRIAR = "CRIAR", "Registo acrescentado"
        ALTERAR = "ALTERAR", "Registo alterado"

    entry = models.ForeignKey(
        TimeEntry, verbose_name="registo", on_delete=models.CASCADE, related_name="corrections"
    )
    kind = models.CharField("tipo", max_length=10, choices=Kind.choices)
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="corrigido por", on_delete=models.PROTECT, related_name="+"
    )
    reason = models.CharField("motivo", max_length=200)
    corrected_at = models.DateTimeField("corrigido em", default=timezone.now)
    # Nulos num registo acrescentado, e nas correções anteriores à Fase 5,
    # cujo valor antigo se perdeu (`previous_known` a falso).
    old_check_in = models.DateTimeField("entrada anterior", null=True, blank=True)
    old_check_out = models.DateTimeField("saída anterior", null=True, blank=True)
    new_check_in = models.DateTimeField("entrada nova")
    new_check_out = models.DateTimeField("saída nova", null=True, blank=True)
    previous_known = models.BooleanField("valor anterior conhecido", default=True)

    class Meta:
        verbose_name = "correção de registo"
        verbose_name_plural = "correções de registos"
        ordering = ["-corrected_at", "-pk"]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.entry} · {self.corrected_by}"


class CorrectionRequest(TimeStampedModel):
    """Pedido de correção feito pelo colaborador (Fase 5). O gerente
    aprova ou recusa; a aprovação aplica a correção pelos serviços, e a
    decisão fica no histórico de correções do registo."""

    class Kind(models.TextChoices):
        CRIAR = "CRIAR", "Acrescentar registo"
        ALTERAR = "ALTERAR", "Alterar registo"

    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        APROVADO = "APROVADO", "Aprovado"
        RECUSADO = "RECUSADO", "Recusado"

    worker = models.ForeignKey(
        "workers.Worker", verbose_name="trabalhador", on_delete=models.CASCADE, related_name="correction_requests"
    )
    entry = models.ForeignKey(
        TimeEntry,
        verbose_name="registo",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="correction_requests",
    )
    kind = models.CharField("tipo", max_length=10, choices=Kind.choices)
    old_check_in = models.DateTimeField("entrada registada", null=True, blank=True)
    old_check_out = models.DateTimeField("saída registada", null=True, blank=True)
    new_check_in = models.DateTimeField("entrada proposta")
    new_check_out = models.DateTimeField("saída proposta")
    note = models.CharField("motivo", max_length=200)
    status = models.CharField("estado", max_length=10, choices=Status.choices, default=Status.PENDENTE)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="decidido por",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    decided_at = models.DateTimeField("decidido em", null=True, blank=True)
    decision_note = models.CharField("observação da decisão", max_length=300, blank=True)

    class Meta:
        verbose_name = "pedido de correção"
        verbose_name_plural = "pedidos de correção"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["entry"],
                condition=models.Q(status="PENDENTE"),
                name="um_pedido_pendente_por_registo",
            ),
            models.CheckConstraint(
                condition=models.Q(new_check_out__gt=models.F("new_check_in")),
                name="pedido_saida_depois_da_entrada",
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.worker} · {self.get_status_display()}"


class MonthClose(TimeStampedModel):
    """Aprovação do mês de um trabalhador (Fase 5). Invariante 8: um mês
    aprovado não muda sem ser reaberto de forma explícita e auditada. A
    reabertura não apaga a aprovação: fica nela, com autor e motivo, e o
    mês aprova-se de novo com uma linha nova."""

    restaurant = models.ForeignKey(
        "core.Restaurant", verbose_name="restaurante", on_delete=models.CASCADE, related_name="month_closes"
    )
    worker = models.ForeignKey(
        "workers.Worker", verbose_name="trabalhador", on_delete=models.CASCADE, related_name="month_closes"
    )
    month = models.DateField("mês")  # sempre o dia 1
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="aprovado por", on_delete=models.PROTECT, related_name="+"
    )
    approved_at = models.DateTimeField("aprovado em", default=timezone.now)
    reopened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="reaberto por",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    reopened_at = models.DateTimeField("reaberto em", null=True, blank=True)
    reopen_reason = models.CharField("motivo da reabertura", max_length=200, blank=True)

    class Meta:
        verbose_name = "fecho do mês"
        verbose_name_plural = "fechos do mês"
        ordering = ["-month", "worker__full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["worker", "month"],
                condition=models.Q(reopened_at__isnull=True),
                name="um_fecho_ativo_por_mes",
            ),
        ]

    def __str__(self):
        return f"{self.worker} · {self.month:%m/%Y}"
