import datetime

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from attendance.forms import CorrectionRequestForm
from attendance.models import CorrectionRequest
from attendance.services import request_correction
from core.mixins import StaffViewMixin
from vacations.forms import VacationRequestForm
from vacations.models import BlockedPeriod
from vacations.services import balance, can_cancel, cancel_request, create_request


def _worker_for(user):
    return getattr(user, "worker", None)


def _formatar(delta):
    total = int(delta.total_seconds() // 60)
    horas, minutos = divmod(total, 60)
    return f"{horas}h{minutos:02d}"


def _totais(worker):
    """Total trabalhado hoje e esta semana, sem as pausas não pagas.
    Turnos abertos contam até agora; cada turno conta no seu dia de
    trabalho, o da entrada (Fase 5)."""
    agora = timezone.now()
    hoje = timezone.localdate()
    inicio_semana = hoje - datetime.timedelta(days=hoje.weekday())

    def soma(desde):
        total = datetime.timedelta()
        for e in worker.time_entries.filter(work_date__gte=desde).prefetch_related("breaks__break_type"):
            total += e.worked(until=agora)
        return total

    total_hoje = soma(hoje)
    total_semana = soma(inicio_semana)
    return {
        "hoje": _formatar(total_hoje),
        "semana": _formatar(total_semana),
    }


def _turnos_de_hoje(worker):
    from shifts.models import Shift

    return Shift.objects.filter(
        worker=worker, state=Shift.State.PUBLICADO, work_date=timezone.localdate()
    ).select_related("template", "work_area")


class StaffHomeView(StaffViewMixin, TemplateView):
    """Ecrã inicial da app do colaborador (Fase 7). Não tem botão de ponto:
    o ponto pica-se no tablet do restaurante. Mostra o estado do dia só
    para leitura, o turno previsto de hoje, os totais e os registos por
    resolver."""

    template_name = "staff/home.html"

    def get(self, request, *args, **kwargs):
        worker = _worker_for(request.user)
        if worker is None:
            return render(request, "staff/sem_ficha.html")
        entry = worker.open_entry
        contexto = {
            "worker": worker,
            "entry": entry,
            "pausa": entry.open_break if entry else None,
            "turnos_hoje": _turnos_de_hoje(worker),
            "totais": _totais(worker),
            # Registos por resolver sem pedido pendente: o colaborador indica a saída.
            "por_resolver": worker.time_entries.unresolved().exclude(
                correction_requests__status=CorrectionRequest.Status.PENDENTE
            ),
        }
        return render(request, self.template_name, contexto)


class StaffHistoryView(StaffViewMixin, TemplateView):
    """Histórico próprio em talões (secção 5)."""

    template_name = "staff/historico.html"

    def get(self, request, *args, **kwargs):
        worker = _worker_for(request.user)
        if worker is None:
            return render(request, "staff/sem_ficha.html")
        entries = (
            worker.time_entries.select_related("corrected_by", "work_area", "restaurant")
            .prefetch_related("breaks__break_type")[:30]
        )
        pendentes = set(
            worker.correction_requests.filter(status=CorrectionRequest.Status.PENDENTE).values_list(
                "entry_id", flat=True
            )
        )
        return render(
            request,
            self.template_name,
            {
                "worker": worker,
                "entries": entries,
                "totais": _totais(worker),
                "com_pedido": pendentes,
                "pedidos": worker.correction_requests.select_related("decided_by")[:10],
                "varias_casas": worker.other_restaurants.exists(),
            },
        )


class StaffVacationsView(StaffViewMixin, View):
    """Pedido de ausência e lista dos pedidos próprios, com o saldo de
    férias e os períodos bloqueados à vista antes de escolher as datas
    (R-060)."""

    def _render(self, request, worker, form):
        hoje = timezone.localdate()
        pedidos = list(worker.vacation_requests.select_related("decided_by", "absence_type")[:20])
        for p in pedidos:
            p.cancelavel = can_cancel(p, today=hoje)
        bloqueios = (
            BlockedPeriod.objects.filter(restaurant=worker.restaurant, end__gte=hoje)
            .exclude(exempt_workers=worker)
            .prefetch_related("absence_types")
        )
        return render(
            request,
            "staff/ferias.html",
            {
                "worker": worker,
                "form": form,
                "pedidos": pedidos,
                "saldo": balance(worker, hoje.year),
                "ano": hoje.year,
                "bloqueios": bloqueios,
            },
        )

    def get(self, request):
        worker = _worker_for(request.user)
        if worker is None:
            return render(request, "staff/sem_ficha.html")
        form = VacationRequestForm(restaurant=worker.restaurant, with_worker=False)
        return self._render(request, worker, form)

    def post(self, request):
        worker = _worker_for(request.user)
        if worker is None:
            return render(request, "staff/sem_ficha.html")
        form = VacationRequestForm(request.POST, restaurant=worker.restaurant, with_worker=False)
        if form.is_valid():
            try:
                pedido = create_request(
                    worker=worker,
                    absence_type=form.cleaned_data["absence_type"],
                    start_date=form.cleaned_data["start_date"],
                    end_date=form.cleaned_data["end_date"],
                    half_day=form.cleaned_data.get("half_day", False),
                    note=form.cleaned_data["request_note"],
                )
                messages.success(
                    request, "Ausência registada" if pedido.status == pedido.Status.APROVADO else "Pedido enviado"
                )
                return redirect("staff:ferias")
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
        return self._render(request, worker, form)


class StaffVacationCancelView(StaffViewMixin, View):
    """Cancelar um pedido pendente, ou aprovado e ainda no futuro (R-056)."""

    def post(self, request, pk):
        worker = _worker_for(request.user)
        if worker is None:
            return render(request, "staff/sem_ficha.html")
        pedido = get_object_or_404(worker.vacation_requests, pk=pk)
        try:
            cancel_request(request_obj=pedido, worker=worker)
            messages.success(request, "Pedido cancelado")
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        return redirect("staff:ferias")


class StaffCorrectionView(StaffViewMixin, View):
    """Pedido de correção de um registo próprio, ou de um registo que falta
    (sem `pk`). O gerente decide no backoffice."""

    def _entry(self, worker, pk):
        if pk is None:
            return None
        return get_object_or_404(worker.time_entries, pk=pk)

    def _casas(self, worker, entry):
        """Num registo que falta, a casa onde trabalhou (Fase 9)."""
        return [] if entry is not None else worker.restaurants()

    def _render(self, request, worker, entry, form):
        return render(request, "staff/correcao.html", {"worker": worker, "entry": entry, "form": form})

    def get(self, request, pk=None):
        worker = _worker_for(request.user)
        if worker is None:
            return render(request, "staff/sem_ficha.html")
        entry = self._entry(worker, pk)
        inicial = {}
        if entry is not None:
            inicial["check_in"] = timezone.localtime(entry.check_in).strftime("%Y-%m-%dT%H:%M")
            if entry.check_out:
                inicial["check_out"] = timezone.localtime(entry.check_out).strftime("%Y-%m-%dT%H:%M")
        return self._render(request, worker, entry, CorrectionRequestForm(initial=inicial, casas=self._casas(worker, entry)))

    def post(self, request, pk=None):
        worker = _worker_for(request.user)
        if worker is None:
            return render(request, "staff/sem_ficha.html")
        entry = self._entry(worker, pk)
        casas = self._casas(worker, entry)
        form = CorrectionRequestForm(request.POST, casas=casas)
        if form.is_valid():
            escolhida = form.cleaned_data.get("restaurant")
            try:
                request_correction(
                    worker=worker,
                    entry=entry,
                    restaurant=next((c for c in casas if c.pk == escolhida), None),
                    note=form.cleaned_data["note"],
                    check_in=form.cleaned_data["check_in"],
                    check_out=form.cleaned_data["check_out"],
                )
                messages.success(request, "Pedido de correção enviado")
                return redirect("staff:historico")
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
        return self._render(request, worker, entry, form)


class StaffShiftsView(StaffViewMixin, TemplateView):
    """Os meus turnos: os publicados e as folgas dos próximos 14 dias. Um
    turno em rascunho ou em reserva nunca aparece (invariante 10)."""

    template_name = "staff/turnos.html"

    def get(self, request, *args, **kwargs):
        from shifts.models import RestDay, Shift

        worker = _worker_for(request.user)
        if worker is None:
            return render(request, "staff/sem_ficha.html")
        hoje = timezone.localdate()
        fim = hoje + datetime.timedelta(days=13)
        turnos = Shift.objects.filter(
            worker=worker, state=Shift.State.PUBLICADO, work_date__range=(hoje, fim)
        ).select_related("template", "work_area", "restaurant")
        folgas = set(
            RestDay.objects.filter(
                worker=worker, state=RestDay.State.PUBLICADO, date__range=(hoje, fim)
            ).values_list("date", flat=True)
        )
        dias = []
        for i in range(14):
            dia = hoje + datetime.timedelta(days=i)
            dias.append({"dia": dia, "turnos": [t for t in turnos if t.work_date == dia], "folga": dia in folgas})
        return render(
            request,
            self.template_name,
            {"worker": worker, "dias": dias, "hoje": hoje, "varias_casas": worker.other_restaurants.exists()},
        )


class StaffConsumptionView(StaffViewMixin, TemplateView):
    """Os meus consumos (Fase 12): os do mês, com o valor ao custo. Nunca os
    dos outros (secção 7)."""

    template_name = "staff/consumos.html"

    def get(self, request, *args, **kwargs):
        from attendance.month import month_range, next_month, previous_month
        from inventory.models import InternalConsumption

        worker = _worker_for(request.user)
        if worker is None:
            return render(request, "staff/sem_ficha.html")
        hoje = timezone.localdate()
        try:
            mes = datetime.datetime.strptime(request.GET.get("mes", ""), "%Y-%m").date()
        except ValueError:
            mes = hoje.replace(day=1)
        inicio, fim = month_range(mes)
        consumos = list(
            InternalConsumption.objects.filter(worker=worker, consumed_on__range=(inicio, fim), cancelled_at__isnull=True)
            .prefetch_related("lines__item")
            .order_by("-consumed_on", "-id")
        )
        valores = [c.value() for c in consumos]
        return render(
            request,
            self.template_name,
            {
                "worker": worker,
                "mes": mes,
                "mes_anterior": previous_month(mes),
                "mes_seguinte": next_month(mes) if next_month(mes) <= hoje else None,
                "consumos": consumos,
                "total": sum((v for v in valores if v is not None), 0),
                "refeicoes": sum(1 for c in consumos if c.reason == InternalConsumption.Reason.REFEICAO),
            },
        )
