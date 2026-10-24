"""
Fecho do mês (Fase 5). O gerente aprova o mês por trabalhador quando não
restam registos por resolver nem pedidos de correção pendentes (R-016).
Depois de aprovado, o mês fica bloqueado (invariante 8) até ser reaberto
com motivo. A exportação CSV do mês aprovado substitui a integração com
payroll (BR-005).
"""
import csv
import datetime
import io

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import CorrectionRequest, MonthClose, TimeEntry


def month_start(day):
    return day.replace(day=1)


def next_month(month):
    return (month.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)


def previous_month(month):
    return (month.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)


def month_range(month):
    """(primeiro dia, último dia) do mês."""
    inicio = month_start(month)
    return inicio, next_month(inicio) - datetime.timedelta(days=1)


def is_closed(worker, day):
    """O mês do dia está aprovado para este trabalhador?"""
    return MonthClose.objects.filter(worker=worker, month=month_start(day), reopened_at__isnull=True).exists()


def ensure_open(worker, *days):
    """Recusa uma alteração que toque num mês aprovado (invariante 8)."""
    for day in days:
        if day is not None and is_closed(worker, day):
            raise ValidationError(
                f"O mês de {day:%m/%Y} de {worker.full_name} já foi aprovado e não aceita alterações. "
                "Para corrigir, o gerente tem de o reabrir."
            )


def pending_items(worker, month):
    """O que impede a aprovação: registos por resolver e pedidos de
    correção pendentes no mês."""
    inicio, fim = month_range(month)
    por_resolver = TimeEntry.objects.filter(worker=worker, work_date__range=(inicio, fim)).unresolved()
    pedidos = CorrectionRequest.objects.filter(worker=worker, status=CorrectionRequest.Status.PENDENTE).filter(
        Q(entry__work_date__range=(inicio, fim))
        | Q(entry__isnull=True, new_check_in__date__range=(inicio, fim))
    )
    return {"por_resolver": por_resolver.count(), "pedidos": pedidos.count()}


def approve_month(*, worker, month, user):
    month = month_start(month)
    if month >= month_start(timezone.localdate()):
        raise ValidationError("Só se aprova um mês que já terminou.")
    with transaction.atomic():
        if MonthClose.objects.select_for_update().filter(
            worker=worker, month=month, reopened_at__isnull=True
        ).exists():
            raise ValidationError(f"O mês de {worker.full_name} já está aprovado.")
        falta = pending_items(worker, month)
        if falta["por_resolver"] or falta["pedidos"]:
            partes = []
            if falta["por_resolver"]:
                partes.append(f"{falta['por_resolver']} registo(s) por resolver")
            if falta["pedidos"]:
                partes.append(f"{falta['pedidos']} pedido(s) de correção pendente(s)")
            raise ValidationError(f"{worker.full_name}: faltam {' e '.join(partes)}.")
        return MonthClose.objects.create(
            restaurant=worker.restaurant, worker=worker, month=month, approved_by=user
        )


def approve_ready(*, workers, month, user):
    """Aprova todos os trabalhadores prontos. Devolve (aprovados, recusados)
    com os motivos dos recusados."""
    aprovados, recusados = [], []
    for w in workers:
        if is_closed(w, month):
            continue
        try:
            approve_month(worker=w, month=month, user=user)
            aprovados.append(w)
        except ValidationError as exc:
            recusados.append((w, exc.messages[0]))
    return aprovados, recusados


def reopen_month(*, worker, month, user, reason):
    if not reason or not reason.strip():
        raise ValidationError("Diga porque reabre o mês: o motivo fica registado.")
    with transaction.atomic():
        fecho = (
            MonthClose.objects.select_for_update()
            .filter(worker=worker, month=month_start(month), reopened_at__isnull=True)
            .first()
        )
        if fecho is None:
            raise ValidationError("Este mês não está aprovado.")
        fecho.reopened_by = user
        fecho.reopened_at = timezone.now()
        fecho.reopen_reason = reason.strip()
        fecho.save(update_fields=["reopened_by", "reopened_at", "reopen_reason", "updated_at"])
        return fecho


def _horas(delta):
    minutos = int(delta.total_seconds() // 60)
    return f"{minutos // 60}:{minutos % 60:02d}"


def month_rows(worker, month):
    """Linhas do mês de um trabalhador: uma por dia de trabalho com
    registos ou ausência aprovada, mais o total."""
    from vacations.models import VacationRequest

    inicio, fim = month_range(month)
    entradas = (
        TimeEntry.objects.filter(worker=worker, work_date__range=(inicio, fim))
        .resolved()
        .select_related("work_area")
        .prefetch_related("breaks__break_type")
        .order_by("check_in")
    )
    ausencias = VacationRequest.objects.filter(
        worker=worker, status=VacationRequest.Status.APROVADO, start_date__lte=fim, end_date__gte=inicio
    ).select_related("absence_type")
    por_dia = {}
    for e in entradas:
        por_dia.setdefault(e.work_date, {"entradas": [], "ausencia": None})["entradas"].append(e)
    for a in ausencias:
        dia = max(a.start_date, inicio)
        while dia <= min(a.end_date, fim):
            por_dia.setdefault(dia, {"entradas": [], "ausencia": None})["ausencia"] = a
            dia += datetime.timedelta(days=1)
    linhas, total = [], datetime.timedelta()
    for dia in sorted(por_dia):
        info = por_dia[dia]
        trabalhado = sum((e.worked() for e in info["entradas"]), datetime.timedelta())
        pausas = sum((e.unpaid_break_time() for e in info["entradas"]), datetime.timedelta())
        total += trabalhado
        linhas.append(
            {
                "dia": dia,
                "entradas": info["entradas"],
                "pausas": pausas,
                "trabalhado": trabalhado,
                "ausencia": info["ausencia"],
            }
        )
    return linhas, total


def export_csv(workers, month):
    """CSV do mês aprovado, para o contabilista. Só os trabalhadores com o
    mês aprovado entram. Separador ';' e decimais com vírgula, como o
    Excel em português espera."""
    saida = io.StringIO()
    escrita = csv.writer(saida, delimiter=";")
    escrita.writerow(
        ["Trabalhador", "Dia", "Entrada", "Saída", "Pausas não pagas", "Horas trabalhadas", "Área", "Ausência"]
    )
    totais = []
    for w in workers:
        if not is_closed(w, month):
            continue
        linhas, total = month_rows(w, month)
        for l in linhas:
            entradas = l["entradas"]
            escrita.writerow(
                [
                    w.full_name,
                    l["dia"].isoformat(),
                    " | ".join(f"{timezone.localtime(e.check_in):%H:%M}" for e in entradas),
                    " | ".join(f"{timezone.localtime(e.check_out):%H:%M}" for e in entradas if e.check_out),
                    _horas(l["pausas"]) if entradas else "",
                    _horas(l["trabalhado"]) if entradas else "",
                    " | ".join(sorted({e.work_area.name for e in entradas if e.work_area})),
                    l["ausencia"].absence_type.name if l["ausencia"] else "",
                ]
            )
        totais.append((w, total))
    escrita.writerow([])
    escrita.writerow(["Totais do mês", "", "", "", "", "Horas trabalhadas"])
    for w, total in totais:
        escrita.writerow([w.full_name, "", "", "", "", _horas(total)])
    return "﻿" + saida.getvalue()
