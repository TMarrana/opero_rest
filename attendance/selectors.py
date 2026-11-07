"""Consultas de leitura do ponto: perguntas do tipo «quem?» que várias
páginas têm de responder da mesma maneira."""
from django.db.models import Q
from django.utils import timezone

from core import exports
from core.utils import workers_scope
from workers.models import Worker

from . import desvios
from .models import TimeEntry
from .month import month_range, previous_month
from .services import overlapping


def workers_for_month(qs, month):
    """Os trabalhadores que pertencem ao fecho de um mês (qualquer dia do mês).

    Entra quem já tinha começado até ao fim do mês e: está ativo sem data de
    saída, ou saiu no mês ou depois, ou tem registos de ponto (não anulados)
    nesse mês. Assim quem saiu a meio do mês continua no fecho e no CSV, e
    quem só começa no mês seguinte não aparece como por aprovar."""
    inicio, fim = month_range(month)
    ja_comecou = Q(start_date__isnull=True) | Q(start_date__lte=fim)
    nesse_mes = (
        Q(is_active=True, end_date__isnull=True)
        | Q(end_date__gte=inicio)
        | Q(
            time_entries__work_date__range=(inicio, fim),
            time_entries__annulled_at__isnull=True,
        )
    )
    return qs.filter(ja_comecou).filter(nesse_mes).distinct().order_by("full_name")


def overlapping_entries(request, now=None):
    """Os registos desta casa, do mês anterior para cá, que se sobrepõem a
    outro registo da mesma pessoa (em qualquer casa): podem ser erros. Os
    meses mais antigos já foram fechados."""
    now = now or timezone.now()
    desde = previous_month(timezone.localdate(now))
    workers = workers_scope(request, Worker.objects.all())
    todos = list(TimeEntry.objects.filter(worker__in=workers, work_date__gte=desde).select_related("worker"))
    ids = overlapping(todos, now=now)
    return sorted(
        (e for e in todos if e.pk in ids and e.restaurant_id == request.restaurant.pk),
        key=lambda e: (e.worker.full_name, e.check_in),
    )


def tabela_registos(restaurant, inicio, fim):
    """Os registos de ponto de uma casa num período (Fase 15): um por linha,
    com as horas como no ecrã. Um registo por resolver conta zero."""
    agora = timezone.now()
    entradas = (
        TimeEntry.objects.filter(restaurant=restaurant, work_date__range=(inicio, fim))
        .select_related("worker__restaurant", "work_area", "corrected_by")
        .prefetch_related("breaks__break_type")
        .order_by("work_date", "worker__full_name", "check_in")
    )
    linhas = []
    for e in entradas:
        if e.is_unresolved(now=agora):
            estado = "Por resolver"
        elif e.is_open:
            estado = "Em turno"
        else:
            estado = ""
        linhas.append(
            [
                e.worker.full_name,
                e.worker.restaurant.name,
                e.work_date,
                e.check_in,
                e.check_out,
                e.unpaid_break_time(until=e.check_out or agora),
                e.worked(until=agora),
                e.work_area.name if e.work_area else "",
                e.get_source_display(),
                estado,
                str(e.corrected_by) if e.corrected_by else "",
                e.correction_reason,
            ]
        )
    return exports.Tabela(
        titulo="Ponto",
        colunas=["Trabalhador", "Casa principal", "Dia", "Entrada", "Saída", "Pausas não pagas (h)", "Trabalhado (h)",
                 "Área", "Origem", "Estado", "Corrigido por", "Motivo da correção"],
        linhas=linhas,
        formatos=[exports.TEXTO, exports.TEXTO, exports.DATA, exports.DATAHORA, exports.DATAHORA, exports.HORAS, exports.HORAS],
    )


def desvios_do_dia(turnos, registos, agora):
    """Planeado contra realizado, em frases (ver `attendance.desvios`):
    cada registo compara-se com o turno com que coincide."""
    return desvios.textos(turnos, registos, agora)
