import datetime

from django.contrib import messages
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import TemplateView

from core.mixins import ManagerRequiredMixin
from core.utils import restaurant_scope
from workers.models import Worker

from .forms import CorrectionDecisionForm, EntryCorrectionForm
from .models import CorrectionRequest, TimeEntry
from .services import add_manual_entry, correct_entry, decide_correction


class TeamDayView(ManagerRequiredMixin, TemplateView):
    """Ponto da equipa num dia de trabalho: quem esteve, quem está em turno
    e o que falta. Um turno que passa a meia-noite aparece só no dia da
    entrada (Fase 5); um turno de um dia anterior ainda aberto aparece
    também, assinalado como saída em falta."""

    template_name = "manage/attendance/dia.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        dia = parse_date(self.request.GET.get("dia", "") or "") or timezone.localdate()
        workers = restaurant_scope(self.request.user, Worker.objects.filter(is_active=True))
        entries = (
            TimeEntry.objects.filter(worker__in=workers)
            .filter(Q(work_date=dia) | Q(work_date__lt=dia, check_out__isnull=True))
            .select_related("worker", "corrected_by", "work_area")
            .prefetch_related("breaks__break_type")
            .order_by("check_in")
        )
        por_worker = {w.pk: [] for w in workers}
        for e in entries:
            por_worker.setdefault(e.worker_id, []).append(e)
        agora = timezone.now()
        linhas = []
        for w in workers:
            registos = por_worker.get(w.pk, [])
            do_dia = [r for r in registos if r.work_date == dia]
            linhas.append(
                {
                    "worker": w,
                    "registos": registos,
                    "em_turno": any(r.is_open for r in registos),
                    "por_resolver": any(r.is_unresolved(now=agora) for r in registos),
                    "total": sum((r.worked(until=agora) for r in do_dia), datetime.timedelta()),
                }
            )
        ctx["linhas"] = linhas
        ctx["dia"] = dia
        ctx["dia_anterior"] = dia - datetime.timedelta(days=1)
        ctx["dia_seguinte"] = dia + datetime.timedelta(days=1)
        ctx["hoje"] = timezone.localdate()
        ctx["pedidos_pendentes"] = _scoped_requests(self.request.user).filter(
            status=CorrectionRequest.Status.PENDENTE
        ).count()
        ctx["total_por_resolver"] = (
            TimeEntry.objects.filter(worker__in=workers).unresolved(now=agora).count()
        )
        return ctx


class EntryCorrectionView(ManagerRequiredMixin, View):
    """Correção auditada de um registo (invariante 5): motivo e autor
    obrigatórios, gravados no próprio registo."""

    def _get_entry(self, request, pk):
        return get_object_or_404(
            restaurant_scope(
                request.user, TimeEntry.objects.select_related("worker"), field="worker__restaurant"
            ),
            pk=pk,
        )

    def _contexto(self, entry, form):
        return {
            "form": form,
            "entry": entry,
            "correcoes": entry.corrections.select_related("corrected_by"),
        }

    def get(self, request, pk):
        entry = self._get_entry(request, pk)
        form = EntryCorrectionForm(
            initial={
                "check_in": timezone.localtime(entry.check_in).strftime("%Y-%m-%dT%H:%M"),
                "check_out": timezone.localtime(entry.check_out).strftime("%Y-%m-%dT%H:%M")
                if entry.check_out
                else "",
            }
        )
        return render(request, "manage/attendance/corrigir.html", self._contexto(entry, form))

    def post(self, request, pk):
        entry = self._get_entry(request, pk)
        form = EntryCorrectionForm(request.POST)
        if form.is_valid():
            try:
                correct_entry(
                    entry=entry,
                    user=request.user,
                    reason=form.cleaned_data["reason"],
                    check_in=form.cleaned_data["check_in"],
                    check_out=form.cleaned_data["check_out"],
                )
                messages.success(request, "Registo corrigido")
                dia = entry.work_date.isoformat()
                return redirect(f"/gestao/ponto/?dia={dia}")
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
        return render(request, "manage/attendance/corrigir.html", self._contexto(entry, form))


class EntryAddView(ManagerRequiredMixin, View):
    """Acrescentar um registo em falta — nasce já como correção auditada."""

    def _get_worker(self, request, pk):
        return get_object_or_404(restaurant_scope(request.user, Worker.objects.all()), pk=pk)

    def get(self, request, pk):
        worker = self._get_worker(request, pk)
        dia = parse_date(request.GET.get("dia", "") or "") or timezone.localdate()
        form = EntryCorrectionForm(initial={"check_in": f"{dia.isoformat()}T09:00"})
        return render(request, "manage/attendance/acrescentar.html", {"form": form, "worker": worker})

    def post(self, request, pk):
        worker = self._get_worker(request, pk)
        form = EntryCorrectionForm(request.POST)
        if form.is_valid():
            try:
                entry = add_manual_entry(
                    worker=worker,
                    user=request.user,
                    reason=form.cleaned_data["reason"],
                    check_in=form.cleaned_data["check_in"],
                    check_out=form.cleaned_data["check_out"],
                )
                messages.success(request, "Registo acrescentado")
                dia = entry.work_date.isoformat()
                return redirect(f"/gestao/ponto/?dia={dia}")
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
        return render(request, "manage/attendance/acrescentar.html", {"form": form, "worker": worker})


def _scoped_requests(user):
    return restaurant_scope(
        user,
        CorrectionRequest.objects.select_related("worker", "entry", "decided_by"),
        field="worker__restaurant",
    )


class CorrectionRequestListView(ManagerRequiredMixin, TemplateView):
    """Pedidos de correção dos colaboradores: pendentes primeiro, e os
    registos por resolver que ainda não têm pedido."""

    template_name = "manage/attendance/pedidos.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = _scoped_requests(self.request.user)
        ctx["pendentes"] = qs.filter(status=CorrectionRequest.Status.PENDENTE).order_by("created_at")
        ctx["decididos"] = qs.exclude(status=CorrectionRequest.Status.PENDENTE).order_by("-decided_at")[:30]
        workers = restaurant_scope(self.request.user, Worker.objects.all())
        ctx["por_resolver"] = (
            TimeEntry.objects.filter(worker__in=workers)
            .unresolved()
            .exclude(correction_requests__status=CorrectionRequest.Status.PENDENTE)
            .select_related("worker")
            .order_by("check_in")
        )
        ctx["form_decisao"] = CorrectionDecisionForm()
        return ctx


class CorrectionDecideView(ManagerRequiredMixin, View):
    def post(self, request, pk, acao):
        pedido = get_object_or_404(_scoped_requests(request.user), pk=pk)
        form = CorrectionDecisionForm(request.POST)
        form.is_valid()
        try:
            decide_correction(
                request_obj=pedido,
                user=request.user,
                approve=(acao == "aprovar"),
                note=form.cleaned_data.get("decision_note", ""),
            )
            messages.success(request, "Pedido aprovado" if acao == "aprovar" else "Pedido recusado")
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        return redirect("attendance:pedidos")
