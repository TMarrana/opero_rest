import datetime
import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views import View
from django.views.generic import TemplateView

from attendance.services import close_shift, open_shift
from core.mixins import StaffViewMixin
from vacations.forms import VacationRequestForm
from vacations.models import VacationRequest


def _worker_for(user):
    return getattr(user, "worker", None)


def _formatar(delta):
    total = int(delta.total_seconds() // 60)
    horas, minutos = divmod(total, 60)
    return f"{horas}h{minutos:02d}"


def _totais(worker):
    """Total trabalhado hoje e esta semana. Turnos abertos contam até
    agora; cada turno conta no dia da entrada (simplificação assumida)."""
    agora = timezone.now()
    hoje = timezone.localdate()
    inicio_semana = hoje - datetime.timedelta(days=hoje.weekday())

    def soma(desde):
        limite = timezone.make_aware(datetime.datetime.combine(desde, datetime.time.min))
        total = datetime.timedelta()
        for e in worker.time_entries.filter(check_in__gte=limite):
            total += (e.check_out or agora) - e.check_in
        return total

    total_hoje = soma(hoje)
    total_semana = soma(inicio_semana)
    return {
        "hoje": _formatar(total_hoje) if total_hoje else "—",
        "semana": _formatar(total_semana) if total_semana else "—",
    }


def _contexto_ponto(worker):
    entry = worker.open_entry
    return {
        "worker": worker,
        "entry": entry,
        "em_turno": entry is not None,
        "totais": _totais(worker),
    }


class StaffHomeView(StaffViewMixin, TemplateView):
    """Ecrã de ponto do colaborador: o botão é o ecrã (secção 5)."""

    template_name = "staff/home.html"

    def get(self, request, *args, **kwargs):
        worker = _worker_for(request.user)
        if worker is None:
            return render(request, "staff/sem_ficha.html")
        return render(request, self.template_name, _contexto_ponto(worker))


class MarkView(StaffViewMixin, View):
    """Alterna o estado do turno. Um único hx-post devolve o fragmento do
    botão já no novo estado. Aceita `marcado_em` da fila offline — o
    timestamp é o do momento da marcação, não o do envio."""

    def post(self, request):
        worker = _worker_for(request.user)
        if worker is None:
            return render(request, "staff/sem_ficha.html")
        momento = timezone.now()
        marcado_em = request.POST.get("marcado_em", "")
        if marcado_em:
            parsed = parse_datetime(marcado_em)
            if parsed is not None:
                if timezone.is_naive(parsed):
                    parsed = timezone.make_aware(parsed)
                # Nunca aceitar marcações no futuro.
                momento = min(parsed, timezone.now())
        try:
            if worker.open_entry:
                close_shift(worker=worker, at=momento)
                texto = "Saída registada"
            else:
                open_shift(worker=worker, at=momento)
                texto = "Entrada registada"
            tom = "sucesso"
        except ValidationError as exc:
            texto, tom = exc.messages[0], "erro"
        resp = render(request, "partials/staff/ponto.html", _contexto_ponto(worker))
        resp["HX-Trigger"] = json.dumps({"toast": {"texto": texto, "tom": tom}})
        return resp


class StaffHistoryView(StaffViewMixin, TemplateView):
    """Histórico próprio em talões (secção 5)."""

    template_name = "staff/historico.html"

    def get(self, request, *args, **kwargs):
        worker = _worker_for(request.user)
        if worker is None:
            return render(request, "staff/sem_ficha.html")
        entries = worker.time_entries.select_related("corrected_by")[:30]
        return render(
            request,
            self.template_name,
            {"worker": worker, "entries": entries, "totais": _totais(worker)},
        )


class StaffVacationsView(StaffViewMixin, View):
    """Pedido de férias em três campos e lista dos pedidos próprios."""

    def _render(self, request, worker, form):
        pedidos = worker.vacation_requests.select_related("decided_by")[:20]
        return render(request, "staff/ferias.html", {"worker": worker, "form": form, "pedidos": pedidos})

    def get(self, request):
        worker = _worker_for(request.user)
        if worker is None:
            return render(request, "staff/sem_ficha.html")
        form = VacationRequestForm(restaurant=worker.restaurant)
        form.fields.pop("worker")
        return self._render(request, worker, form)

    def post(self, request):
        worker = _worker_for(request.user)
        if worker is None:
            return render(request, "staff/sem_ficha.html")
        form = VacationRequestForm(request.POST, restaurant=worker.restaurant)
        form.fields.pop("worker")
        if form.is_valid():
            pedido = form.save(commit=False)
            pedido.worker = worker
            pedido.status = VacationRequest.Status.PENDENTE
            pedido.save()
            messages.success(request, "Pedido enviado")
            return redirect("staff:ferias")
        return self._render(request, worker, form)
