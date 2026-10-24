"""Ausências: contagem de dias, saldo, pedido, decisão e cancelamento.
Decisões sempre com autor, data e observação (invariante 5)."""
import datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .holidays import national_holidays
from .models import Allowance, BlockedPeriod, Holiday, VacationRequest

ZERO = Decimal("0")


def holidays_between(restaurant, start, end):
    """{data: nome} dos feriados nacionais e do restaurante no período."""
    feriados = {}
    for ano in range(start.year, end.year + 1):
        feriados.update({d: n for d, n in national_holidays(ano).items() if start <= d <= end})
    for h in Holiday.objects.filter(restaurant=restaurant, date__range=(start, end)):
        feriados[h.date] = h.name
    return feriados


def count_days(worker, start, end, half_day=False):
    """Dias de ausência: os dias úteis, de segunda a sexta, sem feriados.
    Na Fase 6 os dias sem turno planeado e as folgas também deixam de
    contar (R-037, R-067). Meio dia conta 0,5."""
    feriados = holidays_between(worker.restaurant, start, end)
    dias = 0
    dia = start
    while dia <= end:
        if dia.weekday() < 5 and dia not in feriados:
            dias += 1
        dia += datetime.timedelta(days=1)
    if half_day and dias:
        return Decimal("0.5")
    return Decimal(dias)


def allowance_for(worker, year):
    """O saldo do ano, ou um saldo por guardar com o valor por defeito."""
    saldo = Allowance.objects.filter(worker=worker, year=year).first()
    if saldo is None:
        saldo = Allowance(worker=worker, year=year, days=Decimal(settings.VACATION_DEFAULT_DAYS))
    return saldo


def balance(worker, year, on=None):
    """Saldo de férias de um ano. Só os pedidos aprovados descontam
    (R-053). Os dias transitados gastam-se primeiro, nos pedidos que
    começam até à data em que caducam; o que sobrar caduca (R-066).

    Devolve {total, transitados, usados, disponiveis, caducados}."""
    on = on or timezone.localdate()
    saldo = allowance_for(worker, year)
    expira = saldo.carry_over_expires_on
    transitados_restantes = saldo.carried_over
    dias_restantes = saldo.days
    usados = ZERO
    aprovados = VacationRequest.objects.filter(
        worker=worker,
        status=VacationRequest.Status.APROVADO,
        absence_type__deducts_balance=True,
        start_date__year=year,
    ).order_by("start_date")
    for pedido in aprovados:
        usados += pedido.days_taken
        falta = pedido.days_taken
        if expira is None or pedido.start_date <= expira:
            do_transitado = min(falta, transitados_restantes)
            transitados_restantes -= do_transitado
            falta -= do_transitado
        dias_restantes -= falta
    caducados = transitados_restantes if expira is not None and on > expira else ZERO
    return {
        "total": saldo.days + saldo.carried_over,
        "transitados": saldo.carried_over,
        "usados": usados,
        "caducados": caducados,
        "disponiveis": dias_restantes + transitados_restantes - caducados,
    }


def blocking_period(worker, absence_type, start, end):
    """O primeiro período bloqueado que apanha o pedido, ou None."""
    return (
        BlockedPeriod.objects.filter(restaurant=worker.restaurant, start__lte=end, end__gte=start)
        .filter(Q(absence_types__isnull=True) | Q(absence_types=absence_type))
        .exclude(exempt_workers=worker)
        .distinct()
        .first()
    )


def create_request(*, worker, absence_type, start_date, end_date, half_day=False, note="", created_by=None):
    """Pedido de ausência.

    - Registado pelo gerente (`created_by`), nasce aprovado e com o
      gerente como decisor (R-057).
    - Um tipo que não precisa de aprovação fica aprovado logo (R-051).
    - Um pedido num período bloqueado é recusado na submissão, com o
      motivo (R-060). O gerente não está sujeito a esta regra.
    - Meio dia só num dia e em tipos que o permitam."""
    if absence_type.restaurant_id != worker.restaurant_id or absence_type.archived_at is not None:
        raise ValidationError("Escolha um tipo de ausência em uso.")
    if end_date < start_date:
        raise ValidationError("O fim tem de ser igual ou depois do início.")
    if half_day and (start_date != end_date or not absence_type.half_days):
        raise ValidationError("Meio dia só se pede para um único dia, e nos tipos que o permitem.")
    if created_by is None:
        bloqueio = blocking_period(worker, absence_type, start_date, end_date)
        if bloqueio is not None:
            raise ValidationError(
                f"Não se aceitam pedidos de {bloqueio.start:%d/%m} a {bloqueio.end:%d/%m}: {bloqueio.name}. "
                "Escolha outras datas ou fale com o gerente."
            )
    dias = count_days(worker, start_date, end_date, half_day)
    if absence_type.deducts_balance and dias == 0:
        raise ValidationError("O período escolhido não tem dias úteis: só fins de semana ou feriados.")
    pedido = VacationRequest(
        worker=worker,
        absence_type=absence_type,
        start_date=start_date,
        end_date=end_date,
        half_day=half_day,
        days_taken=dias,
        request_note=note.strip(),
    )
    if created_by is not None:
        pedido.status = VacationRequest.Status.APROVADO
        pedido.decided_by = created_by
        pedido.decided_at = timezone.now()
        pedido.decision_note = "Registado pelo gerente"
    elif not absence_type.requires_approval:
        pedido.status = VacationRequest.Status.APROVADO
        pedido.decided_at = timezone.now()
        pedido.decision_note = "Tipo sem aprovação: aprovado ao registar"
    pedido.save()
    return pedido


def decide_request(*, request_obj, user, approve, note=""):
    with transaction.atomic():
        pedido = VacationRequest.objects.select_for_update().get(pk=request_obj.pk)
        if pedido.status != VacationRequest.Status.PENDENTE:
            raise ValidationError("Este pedido já foi decidido.")
        pedido.status = VacationRequest.Status.APROVADO if approve else VacationRequest.Status.RECUSADO
        pedido.decided_by = user
        pedido.decided_at = timezone.now()
        pedido.decision_note = note.strip()
        pedido.save()
    request_obj.refresh_from_db()
    return pedido


def can_cancel(pedido, today=None):
    """O colaborador cancela um pedido pendente, ou um aprovado que ainda
    não começou (R-056)."""
    today = today or timezone.localdate()
    if pedido.status == VacationRequest.Status.PENDENTE:
        return True
    return pedido.status == VacationRequest.Status.APROVADO and pedido.start_date > today


def cancel_request(*, request_obj, worker):
    with transaction.atomic():
        pedido = VacationRequest.objects.select_for_update().get(pk=request_obj.pk)
        if pedido.worker_id != worker.pk:
            raise ValidationError("Só pode cancelar os seus pedidos.")
        if not can_cancel(pedido):
            raise ValidationError("Este pedido já não se pode cancelar: já começou ou já foi decidido.")
        pedido.status = VacationRequest.Status.CANCELADO
        pedido.cancelled_at = timezone.now()
        pedido.save(update_fields=["status", "cancelled_at", "updated_at"])
    return pedido
