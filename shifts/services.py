"""
Serviços do planeador de turnos (Fase 6).

Uma alteração a um turno publicado tira-o da vista do colaborador até à
publicação seguinte: editar passa-o a rascunho, apagar marca-o para
remoção. Assim o colaborador nunca vê uma versão que o gerente ainda não
confirmou (invariante 10).
"""
import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import RestDay, Shift, WeekPublication, shift_bounds

DIA = datetime.timedelta(days=1)


def week_start(day):
    return day - datetime.timedelta(days=day.weekday())


def week_days(start):
    return [start + datetime.timedelta(days=i) for i in range(7)]


def _check_worker(restaurant, worker):
    if not worker.works_in(restaurant):
        raise ValidationError("Este trabalhador não trabalha nesta casa.")


def create_shift(*, restaurant, worker, day, template=None, start=None, end=None, work_area=None):
    """Turno novo, em rascunho, a partir de um turno guardado ou de horas."""
    _check_worker(restaurant, worker)
    if template is not None:
        if template.restaurant_id != restaurant.pk or template.archived_at is not None:
            raise ValidationError("Escolha um turno guardado em uso.")
        start, end = template.start, template.end
        work_area = work_area or template.work_area
    if start is None or end is None:
        raise ValidationError("Indique o início e o fim do turno.")
    if start == end:
        raise ValidationError("O início e o fim do turno não podem ser iguais.")
    inicio, fim = shift_bounds(day, start, end)
    return Shift.objects.create(
        restaurant=restaurant, worker=worker, start_at=inicio, end_at=fim, work_area=work_area, template=template
    )


def bulk_create(*, restaurant, template, workers, days):
    """Aplica um turno guardado a vários trabalhadores e dias (R-034). Não
    duplica um turno igual que já exista. Devolve quantos criou."""
    criados = 0
    with transaction.atomic():
        for worker in workers:
            for day in days:
                inicio, _ = shift_bounds(day, template.start, template.end)
                if Shift.objects.filter(worker=worker, start_at=inicio, pending_removal=False).exists():
                    continue
                create_shift(restaurant=restaurant, worker=worker, day=day, template=template)
                criados += 1
    return criados


def update_shift(*, shift, start, end, work_area=None):
    """Mudar as horas de um turno. Se estava publicado, volta a rascunho e
    exige nova publicação."""
    if start == end:
        raise ValidationError("O início e o fim do turno não podem ser iguais.")
    shift.start_at, shift.end_at = shift_bounds(timezone.localtime(shift.start_at).date(), start, end)
    shift.work_area = work_area
    if shift.state == Shift.State.PUBLICADO:
        shift.state = Shift.State.RASCUNHO
    shift.save()
    return shift


def remove_shift(*, shift):
    """Um rascunho nunca publicado apaga-se; um turno que já foi publicado
    fica marcado para remoção, para aparecer no resumo da publicação."""
    if shift.was_published:
        shift.pending_removal = True
        shift.state = Shift.State.RASCUNHO
        shift.save(update_fields=["pending_removal", "state", "updated_at"])
    else:
        shift.delete()


def unpublish_shift(*, shift):
    """Voltar um turno publicado a rascunho, com uma ação explícita. Ao
    contrário da Factorial (B-007), aqui pode-se."""
    if shift.state != Shift.State.PUBLICADO:
        raise ValidationError("Só um turno publicado volta a rascunho.")
    shift.state = Shift.State.RASCUNHO
    shift.save(update_fields=["state", "updated_at"])
    return shift


def set_rest_day(*, restaurant, worker, day):
    _check_worker(restaurant, worker)
    outra = RestDay.objects.filter(worker=worker, date=day).exclude(restaurant=restaurant).select_related("restaurant").first()
    if outra is not None:
        raise ValidationError(f"{worker.full_name} já tem folga neste dia, marcada em {outra.restaurant.name}.")
    folga, _ = RestDay.objects.get_or_create(restaurant=restaurant, worker=worker, date=day)
    return folga


def remove_rest_day(*, rest_day):
    rest_day.delete()


def copy_week(*, restaurant, source, target):
    """Copia os turnos e as folgas de uma semana para outra. O que é
    copiado nasce em rascunho (R-038). Devolve (turnos, folgas)."""
    delta = target - source
    turnos = folgas = 0
    with transaction.atomic():
        origem = Shift.objects.filter(
            restaurant=restaurant,
            work_date__range=(source, source + 6 * DIA),
            pending_removal=False,
            worker__is_active=True,
        ).exclude(state=Shift.State.RESERVA)
        for s in origem:
            inicio, fim = s.start_at + delta, s.end_at + delta
            if Shift.objects.filter(worker=s.worker, start_at=inicio, pending_removal=False).exists():
                continue
            Shift.objects.create(
                restaurant=restaurant, worker=s.worker, start_at=inicio, end_at=fim,
                work_area=s.work_area, template=s.template,
            )
            turnos += 1
        for f in RestDay.objects.filter(
            restaurant=restaurant, date__range=(source, source + 6 * DIA), worker__is_active=True
        ):
            _, criada = RestDay.objects.get_or_create(restaurant=restaurant, worker=f.worker, date=f.date + delta)
            folgas += criada
    return turnos, folgas


def _active_shifts(restaurant, inicio, fim):
    return (
        Shift.objects.filter(restaurant=restaurant, work_date__range=(inicio, fim), pending_removal=False)
        .exclude(state=Shift.State.RESERVA)
        .select_related("worker", "template")
        .order_by("worker_id", "start_at")
    )


def conflicts(restaurant, week):
    """Conflitos que impedem a publicação (R-032): turnos sobrepostos da
    mesma pessoa, turno em dia de ausência aprovada ou de folga, e
    descanso abaixo do mínimo entre turnos. Devolve {turno.pk: [motivos]}.

    Quem trabalha em mais de uma casa é uma só pessoa: os turnos e as
    folgas das outras casas do grupo contam para os conflitos, mas só os
    turnos desta casa ficam assinalados (Fase 9)."""
    from vacations.models import VacationRequest

    dias = week_days(week)
    descanso = datetime.timedelta(hours=settings.SHIFT_MIN_REST_HOURS)
    # Um dia para cada lado, para o descanso entre semanas.
    desta_casa = list(_active_shifts(restaurant, dias[0] - DIA, dias[-1] + DIA))
    pessoas = {s.worker_id for s in desta_casa}
    de_outras = (
        Shift.objects.filter(
            worker_id__in=pessoas, work_date__range=(dias[0] - DIA, dias[-1] + DIA), pending_removal=False
        )
        .exclude(restaurant=restaurant)
        .exclude(state=Shift.State.RESERVA)
        .select_related("restaurant")
    )
    turnos = sorted([*desta_casa, *de_outras], key=lambda s: (s.worker_id, s.start_at))
    da_semana = {s.pk for s in desta_casa if dias[0] <= s.work_date <= dias[-1]}
    motivos = {}

    def onde(shift):
        return "" if shift.restaurant_id == restaurant.pk else f" em {shift.restaurant.name}"

    def acrescentar(shift, texto):
        if shift.pk in da_semana:
            motivos.setdefault(shift.pk, []).append(texto)

    por_worker = {}
    for s in turnos:
        por_worker.setdefault(s.worker_id, []).append(s)
    for lista in por_worker.values():
        for anterior, seguinte in zip(lista, lista[1:]):
            if seguinte.start_at < anterior.end_at:
                acrescentar(seguinte, f"Sobrepõe outro turno da mesma pessoa{onde(anterior)}")
                acrescentar(anterior, f"Sobrepõe outro turno da mesma pessoa{onde(seguinte)}")
            elif seguinte.start_at - anterior.end_at < descanso:
                horas = (seguinte.start_at - anterior.end_at).total_seconds() / 3600
                minimo = settings.SHIFT_MIN_REST_HOURS
                acrescentar(
                    seguinte,
                    f"Só {horas:.0f}h de descanso desde o turno anterior{onde(anterior)} (mínimo {minimo}h)",
                )
                if seguinte.restaurant_id != restaurant.pk:
                    acrescentar(
                        anterior,
                        f"Só {horas:.0f}h de descanso até ao turno seguinte{onde(seguinte)} (mínimo {minimo}h)",
                    )

    folgas = set(
        RestDay.objects.filter(worker_id__in=pessoas, date__range=(dias[0], dias[-1])).values_list("worker_id", "date")
    )
    ausencias = VacationRequest.objects.filter(
        worker_id__in=pessoas,
        status=VacationRequest.Status.APROVADO,
        half_day=False,
        start_date__lte=dias[-1],
        end_date__gte=dias[0],
    ).select_related("absence_type")
    for s in turnos:
        if s.pk not in da_semana:
            continue
        if (s.worker_id, s.work_date) in folgas:
            acrescentar(s, "Dia de folga")
        for a in ausencias:
            if a.worker_id == s.worker_id and a.start_date <= s.work_date <= a.end_date:
                acrescentar(s, f"{a.absence_type.name} aprovada")
    return motivos


def changes(restaurant, week):
    """O que muda com a publicação da semana e quem é afetado."""
    dias = week_days(week)
    qs = Shift.objects.filter(restaurant=restaurant, work_date__range=(dias[0], dias[-1])).select_related("worker", "template")
    novos = [s for s in qs if s.state == Shift.State.RASCUNHO and not s.pending_removal and not s.was_published]
    alterados = [s for s in qs if s.state == Shift.State.RASCUNHO and not s.pending_removal and s.was_published]
    removidos = [s for s in qs if s.pending_removal]
    folgas = list(
        RestDay.objects.filter(
            restaurant=restaurant, date__range=(dias[0], dias[-1]), state=RestDay.State.RASCUNHO
        ).select_related("worker")
    )
    afetados = sorted({x.worker.full_name for x in [*novos, *alterados, *removidos, *folgas]})
    return {"novos": novos, "alterados": alterados, "removidos": removidos, "folgas": folgas, "afetados": afetados}


def publish_week(*, restaurant, week, user):
    """Publica a semana. Com conflitos, a publicação é recusada com a
    contagem (secção 9). O colaborador vê as mudanças da próxima vez que
    abre a aplicação: sem push nem email na primeira versão."""
    week = week_start(week)
    with transaction.atomic():
        com_conflito = conflicts(restaurant, week)
        if com_conflito:
            pessoas = Shift.objects.filter(pk__in=com_conflito).values("worker").distinct().count()
            raise ValidationError(
                f"Há {len(com_conflito)} turno(s) com conflito, de {pessoas} trabalhador(es). "
                "Resolva-os antes de publicar."
            )
        mudancas = changes(restaurant, week)
        dias = week_days(week)
        Shift.objects.filter(restaurant=restaurant, work_date__range=(dias[0], dias[-1]), pending_removal=True).delete()
        Shift.objects.filter(
            restaurant=restaurant, work_date__range=(dias[0], dias[-1]), state=Shift.State.RASCUNHO
        ).update(state=Shift.State.PUBLICADO, was_published=True, updated_at=timezone.now())
        RestDay.objects.filter(
            restaurant=restaurant, date__range=(dias[0], dias[-1]), state=RestDay.State.RASCUNHO
        ).update(state=RestDay.State.PUBLICADO, updated_at=timezone.now())
        resumo = (
            f"{len(mudancas['novos'])} novo(s), {len(mudancas['alterados'])} alterado(s), "
            f"{len(mudancas['removidos'])} removido(s), {len(mudancas['folgas'])} folga(s)"
        )
        if mudancas["afetados"]:
            resumo += ". Afetados: " + ", ".join(mudancas["afetados"])
        return WeekPublication.objects.create(restaurant=restaurant, week=week, published_by=user, summary=resumo[:300])


def on_absence_approved(request_obj):
    """Uma ausência de dia inteiro aprovada passa os turnos desses dias a
    reserva, que só o gerente vê (R-033)."""
    if request_obj.half_day:
        return 0
    return (
        Shift.objects.filter(
            worker=request_obj.worker,
            work_date__range=(request_obj.start_date, request_obj.end_date),
            pending_removal=False,
        )
        .exclude(state=Shift.State.RESERVA)
        .update(state=Shift.State.RESERVA, updated_at=timezone.now())
    )


def on_absence_cancelled(request_obj):
    """Ausência aprovada que é cancelada: os turnos em reserva voltam a
    rascunho, e o gerente decide se os publica de novo."""
    return Shift.objects.filter(
        worker=request_obj.worker,
        work_date__range=(request_obj.start_date, request_obj.end_date),
        state=Shift.State.RESERVA,
    ).update(state=Shift.State.RASCUNHO, updated_at=timezone.now())
