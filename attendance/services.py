"""
Serviços de ponto. Invariantes 3 e 4 do plano: um só turno aberto por
trabalhador; não há saída sem entrada prévia. Invariante 7: uma correção
nunca apaga o valor anterior — fica no histórico (EntryCorrection).
"""
import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Break, EntryCorrection, TimeEntry


def open_shift(*, worker, at=None, work_area=None, source=""):
    at = at or timezone.now()
    with transaction.atomic():
        if TimeEntry.objects.select_for_update().filter(worker=worker, check_out__isnull=True).exists():
            raise ValidationError(
                f"{worker.full_name} já tem um turno aberto. Marque a saída antes de nova entrada."
            )
        return TimeEntry.objects.create(worker=worker, check_in=at, work_area=work_area, source=source)


def _open_entry_for_update(worker):
    return TimeEntry.objects.select_for_update().filter(worker=worker, check_out__isnull=True).first()


def close_shift(*, worker, at=None):
    """Marca a saída. Uma pausa aberta fecha à mesma hora."""
    at = at or timezone.now()
    with transaction.atomic():
        entry = _open_entry_for_update(worker)
        if entry is None:
            raise ValidationError(
                f"{worker.full_name} não tem turno aberto. Marque primeiro a entrada."
            )
        if at <= entry.check_in:
            raise ValidationError("A saída tem de ser depois da entrada.")
        pausa = entry.breaks.filter(end__isnull=True).first()
        if pausa is not None:
            pausa.end = max(at, pausa.start + datetime.timedelta(seconds=1))
            pausa.save(update_fields=["end", "updated_at"])
        entry.check_out = at
        entry.save(update_fields=["check_out", "updated_at"])
        return entry


def start_break(*, worker, break_type, at=None):
    """Só com a entrada marcada, e só uma pausa aberta de cada vez (R-004)."""
    at = at or timezone.now()
    if break_type.archived_at is not None:
        raise ValidationError("Este tipo de pausa já não está em uso.")
    with transaction.atomic():
        entry = _open_entry_for_update(worker)
        if entry is None:
            raise ValidationError("Marque primeiro a entrada. Só se começa uma pausa durante o turno.")
        if entry.breaks.filter(end__isnull=True).exists():
            raise ValidationError("Já está em pausa. Termine-a antes de começar outra.")
        if at <= entry.check_in:
            raise ValidationError("A pausa tem de começar depois da entrada.")
        return Break.objects.create(entry=entry, break_type=break_type, start=at)


def end_break(*, worker, at=None):
    at = at or timezone.now()
    with transaction.atomic():
        entry = _open_entry_for_update(worker)
        pausa = entry.breaks.select_for_update().filter(end__isnull=True).first() if entry else None
        if pausa is None:
            raise ValidationError("Não está em pausa.")
        if at <= pausa.start:
            raise ValidationError("O fim da pausa tem de ser depois do início.")
        pausa.end = at
        pausa.save(update_fields=["end", "updated_at"])
        return pausa


def _record_correction(*, entry, user, reason, kind, old_in=None, old_out=None):
    """Grava a linha de histórico e atualiza a cópia da última correção no
    próprio registo. Chamar dentro da transação que alterou o registo."""
    agora = timezone.now()
    EntryCorrection.objects.create(
        entry=entry,
        kind=kind,
        corrected_by=user,
        reason=reason,
        corrected_at=agora,
        old_check_in=old_in,
        old_check_out=old_out,
        new_check_in=entry.check_in,
        new_check_out=entry.check_out,
    )
    entry.corrected_by = user
    entry.correction_reason = reason
    entry.corrected_at = agora
    entry.save(update_fields=["corrected_by", "correction_reason", "corrected_at", "updated_at"])


def correct_entry(*, entry, user, reason, check_in=None, check_out=None):
    """Correção auditada (invariantes 5 e 7): autor e motivo obrigatórios,
    e o valor anterior fica no histórico."""
    if not reason or not reason.strip():
        raise ValidationError("O motivo da correção é obrigatório.")
    with transaction.atomic():
        # Reler com lock: os campos não indicados mantêm o valor atual, não
        # o de uma instância antiga (uma saída marcada entretanto não se perde).
        TimeEntry.objects.select_for_update().filter(pk=entry.pk).first()
        entry.refresh_from_db()
        new_in = check_in or entry.check_in
        new_out = check_out if check_out is not None else entry.check_out
        if new_out is not None and new_out <= new_in:
            raise ValidationError("A saída tem de ser depois da entrada.")
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
        old_in, old_out = entry.check_in, entry.check_out
        entry.check_in = new_in
        entry.check_out = new_out
        entry.save()
        _record_correction(
            entry=entry, user=user, reason=reason.strip(), kind=EntryCorrection.Kind.ALTERAR,
            old_in=old_in, old_out=old_out,
        )
    return entry


def add_manual_entry(*, worker, user, reason, check_in, check_out=None, work_area=None):
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
        entry = TimeEntry.objects.create(
            worker=worker,
            check_in=check_in,
            check_out=check_out,
            work_area=work_area,
            source=TimeEntry.Source.GERENTE,
        )
        _record_correction(entry=entry, user=user, reason=reason.strip(), kind=EntryCorrection.Kind.CRIAR)
        return entry
