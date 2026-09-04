"""
Serviços de ponto. Invariantes 3 e 4 do plano: um só turno aberto por
trabalhador; não há saída sem entrada prévia.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import TimeEntry


def open_shift(*, worker, at=None):
    at = at or timezone.now()
    with transaction.atomic():
        if TimeEntry.objects.select_for_update().filter(worker=worker, check_out__isnull=True).exists():
            raise ValidationError(
                f"{worker.full_name} já tem um turno aberto. Marque a saída antes de nova entrada."
            )
        return TimeEntry.objects.create(worker=worker, check_in=at)


def close_shift(*, worker, at=None):
    at = at or timezone.now()
    with transaction.atomic():
        entry = (
            TimeEntry.objects.select_for_update()
            .filter(worker=worker, check_out__isnull=True)
            .first()
        )
        if entry is None:
            raise ValidationError(
                f"{worker.full_name} não tem turno aberto. Marque primeiro a entrada."
            )
        if at <= entry.check_in:
            raise ValidationError("A saída tem de ser depois da entrada.")
        entry.check_out = at
        entry.save(update_fields=["check_out", "updated_at"])
        return entry


def correct_entry(*, entry, user, reason, check_in=None, check_out=None):
    """Correção auditada (invariante 5): autor e motivo obrigatórios."""
    if not reason or not reason.strip():
        raise ValidationError("O motivo da correção é obrigatório.")
    new_in = check_in or entry.check_in
    new_out = check_out if check_out is not None else entry.check_out
    if new_out is not None and new_out <= new_in:
        raise ValidationError("A saída tem de ser depois da entrada.")
    with transaction.atomic():
        if new_out is None:
            aberto = (
                TimeEntry.objects.select_for_update()
                .filter(worker=entry.worker, check_out__isnull=True)
                .exclude(pk=entry.pk)
            )
            if aberto.exists():
                raise ValidationError(
                    f"{entry.worker.full_name} já tem outro turno aberto; este registo tem de ter saída."
                )
        entry.check_in = new_in
        entry.check_out = new_out
        entry.corrected_by = user
        entry.correction_reason = reason.strip()
        entry.corrected_at = timezone.now()
        entry.save()
    return entry


def add_manual_entry(*, worker, user, reason, check_in, check_out=None):
    """Registo em falta acrescentado pelo gerente — nasce como correção
    auditada, com autor e motivo."""
    if not reason or not reason.strip():
        raise ValidationError("O motivo é obrigatório num registo manual.")
    if check_out is not None and check_out <= check_in:
        raise ValidationError("A saída tem de ser depois da entrada.")
    with transaction.atomic():
        if check_out is None and TimeEntry.objects.select_for_update().filter(
            worker=worker, check_out__isnull=True
        ).exists():
            raise ValidationError(f"{worker.full_name} já tem um turno aberto.")
        return TimeEntry.objects.create(
            worker=worker,
            check_in=check_in,
            check_out=check_out,
            corrected_by=user,
            correction_reason=reason.strip(),
            corrected_at=timezone.now(),
        )
