"""
Planeador de turnos (Fase 6). O gerente planeia a semana em rascunho,
publica-a, e o colaborador só vê o que está publicado (invariante 10).
"""
import datetime

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel


class ShiftTemplate(TimeStampedModel):
    """Turno guardado: «Almoço», «Jantar», «Fecho», «Dobra». Um fim antes
    do início quer dizer que o turno acaba no dia seguinte. Arquiva-se em
    vez de se apagar."""

    restaurant = models.ForeignKey(
        "core.Restaurant", verbose_name="restaurante", on_delete=models.CASCADE, related_name="shift_templates"
    )
    name = models.CharField("nome", max_length=40)
    start = models.TimeField("início")
    end = models.TimeField("fim")
    work_area = models.ForeignKey(
        "core.WorkArea", verbose_name="área", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    archived_at = models.DateTimeField("arquivado em", null=True, blank=True)

    class Meta:
        verbose_name = "turno guardado"
        verbose_name_plural = "turnos guardados"
        ordering = ["start", "name"]

    def __str__(self):
        return f"{self.name} {self.start:%H:%M}–{self.end:%H:%M}"

    def bounds(self, day):
        """(início, fim) com fuso horário para o turno num dia."""
        return shift_bounds(day, self.start, self.end)


def shift_bounds(day, start, end):
    inicio = timezone.make_aware(datetime.datetime.combine(day, start))
    fim_dia = day + datetime.timedelta(days=1) if end <= start else day
    return inicio, timezone.make_aware(datetime.datetime.combine(fim_dia, end))


class Shift(TimeStampedModel):
    """Turno planeado. Conta no dia em que começa, como no ponto.

    Estados: rascunho (só o gerente vê), publicado (o colaborador vê) e
    reserva (o trabalhador tem uma ausência aprovada nesse dia; só o
    gerente vê, para saber que tem um buraco no planeamento — R-033).
    Um turno publicado que se apaga fica marcado para remoção até à
    publicação seguinte."""

    class State(models.TextChoices):
        RASCUNHO = "RASCUNHO", "Rascunho"
        PUBLICADO = "PUBLICADO", "Publicado"
        RESERVA = "RESERVA", "Reserva"

    restaurant = models.ForeignKey(
        "core.Restaurant", verbose_name="restaurante", on_delete=models.CASCADE, related_name="shifts"
    )
    worker = models.ForeignKey(
        "workers.Worker", verbose_name="trabalhador", on_delete=models.CASCADE, related_name="shifts"
    )
    start_at = models.DateTimeField("início")
    end_at = models.DateTimeField("fim")
    work_date = models.DateField("dia de trabalho", db_index=True)
    work_area = models.ForeignKey(
        "core.WorkArea", verbose_name="área", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    template = models.ForeignKey(
        ShiftTemplate, verbose_name="turno guardado", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    state = models.CharField("estado", max_length=10, choices=State.choices, default=State.RASCUNHO)
    # Já esteve publicado: uma alteração ou remoção exige nova publicação
    # e aparece no resumo do que mudou.
    was_published = models.BooleanField("já publicado", default=False)
    pending_removal = models.BooleanField("a remover na publicação", default=False)

    class Meta:
        verbose_name = "turno"
        verbose_name_plural = "turnos"
        ordering = ["start_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(end_at__gt=models.F("start_at")), name="turno_fim_depois_do_inicio"),
        ]

    def __str__(self):
        return f"{self.worker} · {timezone.localtime(self.start_at):%d/%m %H:%M}"

    def save(self, *args, **kwargs):
        self.work_date = timezone.localtime(self.start_at).date()
        super().save(*args, **kwargs)

    @property
    def label(self):
        return self.template.name if self.template else "Turno"

    @property
    def duration(self):
        return self.end_at - self.start_at


class RestDay(TimeStampedModel):
    """Folga planeada. Não desconta dias de férias (R-037)."""

    class State(models.TextChoices):
        RASCUNHO = "RASCUNHO", "Rascunho"
        PUBLICADO = "PUBLICADO", "Publicado"

    restaurant = models.ForeignKey(
        "core.Restaurant", verbose_name="restaurante", on_delete=models.CASCADE, related_name="rest_days"
    )
    worker = models.ForeignKey(
        "workers.Worker", verbose_name="trabalhador", on_delete=models.CASCADE, related_name="rest_days"
    )
    date = models.DateField("dia")
    state = models.CharField("estado", max_length=10, choices=State.choices, default=State.RASCUNHO)

    class Meta:
        verbose_name = "folga"
        verbose_name_plural = "folgas"
        ordering = ["date"]
        constraints = [models.UniqueConstraint(fields=["worker", "date"], name="uma_folga_por_dia")]

    def __str__(self):
        return f"Folga · {self.worker} · {self.date:%d/%m}"


class WeekPublication(models.Model):
    """Registo de cada publicação de uma semana: quem, quando e o resumo."""

    restaurant = models.ForeignKey(
        "core.Restaurant", verbose_name="restaurante", on_delete=models.CASCADE, related_name="+"
    )
    week = models.DateField("semana")  # segunda-feira
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="publicado por", on_delete=models.PROTECT, related_name="+"
    )
    published_at = models.DateTimeField("publicado em", default=timezone.now)
    summary = models.CharField("resumo", max_length=300)

    class Meta:
        verbose_name = "publicação de semana"
        verbose_name_plural = "publicações de semanas"
        ordering = ["-published_at"]
