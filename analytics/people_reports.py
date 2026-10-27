"""
Relatórios de pessoas (Fase 15): presenças e ausências, horas por área, e
atrasos e faltas de marcação face aos turnos publicados. Só o Admin e o
Gerente (secção 7).

Tudo na casa escolhida: as horas e os desvios contam os registos e os turnos
dessa casa, incluindo quem vem de outra (Fase 9). As ausências são da casa
principal, que é quem as aprova, e contam os dias como o pedido os conta
(`vacations.services.count_days`).

Os desvios seguem o ecrã do ponto da equipa: a tolerância é a de
`SHIFT_TOLERANCE_MINUTES`; um turno publicado sem nenhum registo, depois de
começar, é uma falta de marcação; um registo por resolver conta zero horas
(invariante 9), mas conta como presença.
"""
import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from attendance.models import TimeEntry
from shifts.models import Shift
from vacations.models import VacationRequest
from vacations.services import count_days
from workers.models import Worker

ZERO = Decimal(0)
SEM_AREA = "Sem área"


@dataclass
class Desvio:
    dia: datetime.date
    worker: Worker
    tipo: str  # "Falta de marcação", "Atraso", "Saída antes da hora"
    minutos: int | None
    previsto: str


@dataclass
class Pessoa:
    worker: Worker
    dias: set = field(default_factory=set)
    horas: datetime.timedelta = field(default_factory=datetime.timedelta)
    previstas: datetime.timedelta = field(default_factory=datetime.timedelta)
    por_resolver: int = 0
    atrasos: int = 0
    minutos_atraso: int = 0
    saidas_cedo: int = 0
    faltas: int = 0
    ausencias: Decimal = ZERO
    visita: bool = False  # vem de outra casa do grupo (Fase 9)

    @property
    def dias_trabalhados(self):
        return len(self.dias)

    @property
    def diferenca(self):
        """Horas a mais (positivo) ou a menos face ao previsto. Sem turnos
        publicados, não há comparação."""
        if not self.previstas:
            return None
        return self.horas - self.previstas


def _desvios(worker, dia, turnos, registos, agora, tolerancia):
    """Os desvios de um trabalhador num dia, face aos turnos publicados
    desta casa (como `attendance.views._desvios`)."""
    if not turnos:
        return []
    inicio = min(t.start_at for t in turnos)
    fim = max(t.end_at for t in turnos)
    previsto = " + ".join(
        f"{timezone.localtime(t.start_at):%H:%M}–{timezone.localtime(t.end_at):%H:%M}" for t in sorted(turnos, key=lambda t: t.start_at)
    )
    if not registos:
        return [Desvio(dia, worker, "Falta de marcação", None, previsto)] if agora > inicio + tolerancia else []
    desvios = []
    entrada = min(r.check_in for r in registos)
    if entrada > inicio + tolerancia:
        desvios.append(Desvio(dia, worker, "Atraso", int((entrada - inicio).total_seconds() // 60), previsto))
    if all(r.check_out for r in registos):
        saida = max(r.check_out for r in registos)
        if saida < fim - tolerancia:
            desvios.append(Desvio(dia, worker, "Saída antes da hora", int((fim - saida).total_seconds() // 60), previsto))
    return desvios


def pessoas(restaurant, inicio, fim, agora=None):
    """(uma linha por trabalhador, desvios). Entram os ativos da casa
    principal e quem picou ou teve turnos cá no período."""
    agora = agora or timezone.now()
    tolerancia = datetime.timedelta(minutes=settings.SHIFT_TOLERANCE_MINUTES)
    registos = list(
        TimeEntry.objects.filter(restaurant=restaurant, work_date__range=(inicio, fim))
        .select_related("worker")
        .prefetch_related("breaks__break_type")
    )
    turnos = list(
        Shift.objects.filter(
            restaurant=restaurant, work_date__range=(inicio, fim), state=Shift.State.PUBLICADO, pending_removal=False
        ).select_related("worker")
    )
    trabalhadores = {w.pk: w for w in Worker.objects.filter(restaurant=restaurant, is_active=True)}
    for x in (*registos, *turnos):
        trabalhadores.setdefault(x.worker_id, x.worker)
    linhas = {pk: Pessoa(worker=w, visita=w.restaurant_id != restaurant.pk) for pk, w in trabalhadores.items()}

    por_dia_registos, por_dia_turnos = defaultdict(list), defaultdict(list)
    for r in registos:
        p = linhas[r.worker_id]
        p.dias.add(r.work_date)
        if r.is_unresolved(now=agora):
            p.por_resolver += 1
        else:
            p.horas += r.worked(until=agora)
        por_dia_registos[(r.worker_id, r.work_date)].append(r)
    for t in turnos:
        linhas[t.worker_id].previstas += t.duration
        por_dia_turnos[(t.worker_id, t.work_date)].append(t)

    desvios = []
    for (pk, dia), lista in por_dia_turnos.items():
        for d in _desvios(linhas[pk].worker, dia, lista, por_dia_registos.get((pk, dia), []), agora, tolerancia):
            desvios.append(d)
            p = linhas[pk]
            if d.tipo == "Falta de marcação":
                p.faltas += 1
            elif d.tipo == "Atraso":
                p.atrasos += 1
                p.minutos_atraso += d.minutos
            else:
                p.saidas_cedo += 1

    for pedido in _ausencias(restaurant, inicio, fim):
        if pedido.worker_id in linhas:
            linhas[pedido.worker_id].ausencias += _dias_no_periodo(pedido, inicio, fim)

    ordenadas = sorted(linhas.values(), key=lambda p: (p.visita, p.worker.full_name.casefold()))
    desvios.sort(key=lambda d: (d.dia, d.worker.full_name.casefold()))
    return ordenadas, desvios


def _ausencias(restaurant, inicio, fim):
    """As ausências aprovadas dos trabalhadores desta casa principal que tocam
    no período."""
    return VacationRequest.objects.filter(
        worker__restaurant=restaurant,
        status=VacationRequest.Status.APROVADO,
        start_date__lte=fim,
        end_date__gte=inicio,
    ).select_related("worker__restaurant", "absence_type")


def _dias_no_periodo(pedido, inicio, fim):
    """Os dias do pedido que caem no período, contados como o pedido os conta.
    Um pedido todo dentro do período vale os dias que ficaram guardados."""
    if pedido.start_date >= inicio and pedido.end_date <= fim:
        return pedido.days_taken
    return count_days(pedido.worker, max(pedido.start_date, inicio), min(pedido.end_date, fim), pedido.half_day)


def ausencias_por_tipo(restaurant, inicio, fim):
    """Uma linha por tipo de ausência: pedidos aprovados e dias no período."""
    tipos = defaultdict(lambda: {"pedidos": 0, "dias": ZERO, "pessoas": set()})
    for pedido in _ausencias(restaurant, inicio, fim):
        t = tipos[pedido.absence_type.name]
        t["pedidos"] += 1
        t["dias"] += _dias_no_periodo(pedido, inicio, fim)
        t["pessoas"].add(pedido.worker_id)
    return [
        {"tipo": nome, "pedidos": t["pedidos"], "dias": t["dias"], "pessoas": len(t["pessoas"])}
        for nome, t in sorted(tipos.items(), key=lambda kv: -kv[1]["dias"])
    ]


def horas_por_area(restaurant, inicio, fim, agora=None):
    """Horas trabalhadas e previstas por área. Um registo sem área conta em
    «Sem área»."""
    agora = agora or timezone.now()
    areas = defaultdict(lambda: {"horas": datetime.timedelta(), "previstas": datetime.timedelta(), "pessoas": set()})
    for r in (
        TimeEntry.objects.filter(restaurant=restaurant, work_date__range=(inicio, fim))
        .select_related("work_area")
        .prefetch_related("breaks__break_type")
    ):
        a = areas[r.work_area.name if r.work_area else SEM_AREA]
        a["horas"] += r.worked(until=agora)
        a["pessoas"].add(r.worker_id)
    for t in Shift.objects.filter(
        restaurant=restaurant, work_date__range=(inicio, fim), state=Shift.State.PUBLICADO, pending_removal=False
    ).select_related("work_area"):
        areas[t.work_area.name if t.work_area else SEM_AREA]["previstas"] += t.duration
    return [
        {"area": nome, "horas": a["horas"], "previstas": a["previstas"], "pessoas": len(a["pessoas"])}
        for nome, a in sorted(areas.items(), key=lambda kv: (kv[0] == SEM_AREA, -kv[1]["horas"]))
    ]


def presencas_por_mes(restaurant, inicio, fim, agora=None):
    """Por mês do período: pessoas com presença, dias de presença (pessoa ×
    dia), horas trabalhadas e dias de ausência."""
    agora = agora or timezone.now()
    meses = defaultdict(lambda: {"pessoas": set(), "presencas": set(), "horas": datetime.timedelta(), "ausencias": ZERO})
    for r in (
        TimeEntry.objects.filter(restaurant=restaurant, work_date__range=(inicio, fim)).prefetch_related("breaks__break_type")
    ):
        m = meses[r.work_date.replace(day=1)]
        m["pessoas"].add(r.worker_id)
        m["presencas"].add((r.worker_id, r.work_date))
        m["horas"] += r.worked(until=agora)
    for pedido in _ausencias(restaurant, inicio, fim):
        # Um pedido que atravessa meses divide-se pelos dias de cada um.
        mes = max(pedido.start_date, inicio).replace(day=1)
        while mes <= min(pedido.end_date, fim):
            seguinte = (mes.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
            de, ate = max(pedido.start_date, inicio, mes), min(pedido.end_date, fim, seguinte - datetime.timedelta(days=1))
            if de <= ate:
                meses[mes]["ausencias"] += count_days(pedido.worker, de, ate, pedido.half_day)
            mes = seguinte
    return [
        {
            "mes": mes,
            "pessoas": len(m["pessoas"]),
            "presencas": len(m["presencas"]),
            "horas": m["horas"],
            "ausencias": m["ausencias"],
        }
        for mes, m in sorted(meses.items())
    ]
