import datetime

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.generic import TemplateView

from core import exports
from core.mixins import ManagerRequiredMixin
from core.utils import restaurant_scope, workers_scope
from sales.services import dia_de_servico
from shifts.models import Shift
from workers.models import Worker

from . import month as mes
from .forms import CorrectionDecisionForm, EntryCorrectionForm
from .models import CorrectionRequest, MonthClose, TimeEntry
from .selectors import desvios_do_dia, overlapping_entries, tabela_registos, workers_for_month
from .services import add_manual_entry, annul_entry, correct_entry, decide_correction, overlapping


def _voltar(request, padrao):
    """Para onde seguir depois de corrigir ou acrescentar: o `voltar` do
    pedido (ex.: o fecho do mês), se for um caminho deste site; senão
    `padrao`."""
    destino = request.POST.get("voltar") or request.GET.get("voltar") or ""
    if destino and url_has_allowed_host_and_scheme(destino, {request.get_host()}, request.is_secure()):
        return destino
    return padrao


# As páginas de ponto mostram horas que mudam com cada correção: sem cache,
# para que voltar atrás no browser não traga horas antigas.
@method_decorator(never_cache, name="dispatch")
class TeamDayView(ManagerRequiredMixin, TemplateView):
    """Ponto da equipa num dia de trabalho: quem esteve, quem está em turno
    e o que falta. Um turno que passa a meia-noite aparece só no dia da
    entrada (Fase 5); um turno de um dia anterior ainda aberto aparece
    também, assinalado como saída em falta. Só contam os registos e os
    turnos desta casa; quem vem de outra casa aparece nos dias em que cá
    picou ou tinha turno (Fase 9)."""

    template_name = "manage/attendance/dia.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        restaurant = self.request.restaurant
        hoje = dia_de_servico(restaurant)
        dia = parse_date(self.request.GET.get("dia", "") or "") or hoje
        # Quem estava na casa nesse dia: os ativos, quem saiu nesse dia ou
        # depois, e quem picou nesse dia (num dia passado, quem já saiu
        # continua no dia em que trabalhou).
        workers = workers_scope(
            self.request,
            Worker.objects.filter(
                Q(is_active=True) | Q(end_date__gte=dia) | Q(time_entries__work_date=dia)
            ).distinct(),
        )
        entries = (
            TimeEntry.objects.filter(restaurant=restaurant, worker__in=workers)
            .filter(Q(work_date=dia) | Q(work_date__lt=dia, check_out__isnull=True))
            .select_related("worker", "corrected_by", "work_area")
            .prefetch_related("breaks__break_type")
            .order_by("check_in")
        )
        por_worker = {w.pk: [] for w in workers}
        for e in entries:
            por_worker.setdefault(e.worker_id, []).append(e)
        agora = timezone.now()
        previstos = {}
        for t in Shift.objects.filter(
            restaurant=restaurant, worker__in=workers, work_date=dia, state=Shift.State.PUBLICADO
        ).select_related("template"):
            previstos.setdefault(t.worker_id, []).append(t)
        linhas = []
        for w in workers:
            registos = por_worker.get(w.pk, [])
            do_dia = [r for r in registos if r.work_date == dia]
            turnos = previstos.get(w.pk, [])
            visita = w.restaurant_id != restaurant.pk
            if visita and not registos and not turnos:
                continue
            linhas.append(
                {
                    "worker": w,
                    "visita": visita,
                    "registos": registos,
                    "previstos": turnos,
                    "desvios": desvios_do_dia(turnos, do_dia, agora),
                    "em_turno": any(r.is_open for r in registos),
                    "por_resolver": any(r.is_unresolved(now=agora) for r in registos),
                    "total": sum((r.worked(until=agora) for r in do_dia), datetime.timedelta()),
                }
            )
        ctx["linhas"] = linhas
        ctx["sobrepostos"] = overlapping(
            TimeEntry.objects.filter(worker__in=workers, check_in__date__range=(dia - datetime.timedelta(days=1), dia + datetime.timedelta(days=1))),
            now=agora,
        )
        ctx["dia"] = dia
        ctx["dia_anterior"] = dia - datetime.timedelta(days=1)
        ctx["dia_seguinte"] = dia + datetime.timedelta(days=1)
        ctx["hoje"] = hoje
        ctx["pedidos_pendentes"] = _scoped_requests(self.request).filter(
            status=CorrectionRequest.Status.PENDENTE
        ).count()
        ctx["total_por_resolver"] = (
            TimeEntry.objects.filter(restaurant=restaurant).unresolved(now=agora).count()
        )
        return ctx


    def get(self, request, *args, **kwargs):
        formato = exports.formato_pedido(request)
        if formato:
            dia = parse_date(request.GET.get("dia", "") or "") or dia_de_servico(request.restaurant)
            inicio, fim = mes.month_range(dia)
            return exports.responder(
                formato, [tabela_registos(request.restaurant, inicio, fim)], f"ponto-{inicio:%Y-%m}"
            )
        return super().get(request, *args, **kwargs)


class EntryCorrectionView(ManagerRequiredMixin, View):
    """Correção auditada de um registo (invariante 5): motivo e autor
    obrigatórios, gravados no próprio registo."""

    def _get_entry(self, request, pk):
        return get_object_or_404(
            restaurant_scope(request, TimeEntry.objects.select_related("worker")),
            pk=pk,
        )

    def _contexto(self, request, entry, form):
        return {
            "form": form,
            "entry": entry,
            "correcoes": entry.corrections.select_related("corrected_by"),
            "voltar": _voltar(request, f"{reverse('attendance:dia')}?dia={entry.work_date.isoformat()}"),
            "sobreposto": entry.pk in overlapping(
                TimeEntry.objects.filter(
                    worker=entry.worker,
                    check_in__range=(entry.check_in - datetime.timedelta(days=2), entry.check_in + datetime.timedelta(days=2)),
                )
            ),
            "mes_fechado": mes.is_closed(entry.worker, entry.work_date),
            "abrir_apagar": request.GET.get("apagar") == "1",
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
        return render(request, "manage/attendance/corrigir.html", self._contexto(request, entry, form))

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
                return redirect(_voltar(request, f"{reverse('attendance:dia')}?dia={entry.work_date.isoformat()}"))
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
        return render(request, "manage/attendance/corrigir.html", self._contexto(request, entry, form))


class EntryDeleteView(ManagerRequiredMixin, View):
    """Apagar um registo que é um erro (ex.: duplicado). Fica guardado, fora
    das listas e dos totais, com a correção «Registo apagado»."""

    def post(self, request, pk):
        entry = get_object_or_404(restaurant_scope(request, TimeEntry.objects.select_related("worker")), pk=pk)
        voltar = _voltar(request, f"{reverse('attendance:dia')}?dia={entry.work_date.isoformat()}")
        try:
            annul_entry(entry=entry, user=request.user, reason=request.POST.get("reason", "")[:200])
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect(voltar)
        fim = f"{timezone.localtime(entry.check_out):%H:%M}" if entry.check_out else "sem saída"
        messages.success(
            request, f"Registo de {entry.worker.full_name} apagado ({timezone.localtime(entry.check_in):%d/%m %H:%M} → {fim})"
        )
        return redirect(voltar)


class EntryAddView(ManagerRequiredMixin, View):
    """Acrescentar um registo em falta — nasce já como correção auditada,
    na casa ativa."""

    def _get_worker(self, request, pk):
        return get_object_or_404(workers_scope(request, Worker.objects.all()), pk=pk)

    def get(self, request, pk):
        worker = self._get_worker(request, pk)
        dia = parse_date(request.GET.get("dia", "") or "") or timezone.localdate()
        form = EntryCorrectionForm(initial={"check_in": f"{dia.isoformat()}T09:00"})
        return render(request, "manage/attendance/acrescentar.html", self._contexto(request, worker, form, dia))

    def _contexto(self, request, worker, form, dia=None):
        dia = dia or timezone.localdate()
        return {"form": form, "worker": worker, "voltar": _voltar(request, f"{reverse('attendance:dia')}?dia={dia.isoformat()}")}

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
                    restaurant=request.restaurant,
                )
                messages.success(request, "Registo acrescentado")
                return redirect(_voltar(request, f"{reverse('attendance:dia')}?dia={entry.work_date.isoformat()}"))
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
        return render(request, "manage/attendance/acrescentar.html", self._contexto(request, worker, form))


def _scoped_requests(request):
    return restaurant_scope(
        request,
        CorrectionRequest.objects.select_related("worker", "entry", "decided_by"),
    )


class CorrectionRequestListView(ManagerRequiredMixin, TemplateView):
    """Pedidos de correção dos colaboradores: pendentes primeiro, e os
    registos por resolver que ainda não têm pedido."""

    template_name = "manage/attendance/pedidos.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = _scoped_requests(self.request)
        ctx["pendentes"] = qs.filter(status=CorrectionRequest.Status.PENDENTE).order_by("created_at")
        ctx["decididos"] = qs.exclude(status=CorrectionRequest.Status.PENDENTE).order_by("-decided_at")[:30]
        ctx["por_resolver"] = (
            restaurant_scope(self.request, TimeEntry.objects.all())
            .unresolved()
            .exclude(correction_requests__status=CorrectionRequest.Status.PENDENTE)
            .select_related("worker")
            .order_by("check_in")
        )
        ctx["form_decisao"] = CorrectionDecisionForm()
        ctx["sobrepostos"] = overlapping_entries(self.request)
        return ctx


class CorrectionDecideView(ManagerRequiredMixin, View):
    def post(self, request, pk, acao):
        pedido = get_object_or_404(_scoped_requests(request), pk=pk)
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


def _mes_pedido(request):
    """Mês escolhido em ?mes=AAAA-MM; por defeito, o mês anterior."""
    valor = request.GET.get("mes") or request.POST.get("mes") or ""
    try:
        return datetime.datetime.strptime(valor, "%Y-%m").date()
    except ValueError:
        return mes.previous_month(timezone.localdate())


@method_decorator(never_cache, name="dispatch")
class MonthView(ManagerRequiredMixin, View):
    """Fecho do mês: horas por trabalhador, o que falta resolver,
    aprovação (uma a uma ou todos os prontos), reabertura com motivo e
    exportação CSV."""

    def _workers(self, request, escolhido):
        """Quem entra no fecho desse mês, incluindo quem já saiu."""
        return workers_for_month(restaurant_scope(request, Worker.objects.all()), escolhido)

    def _url(self, mes_escolhido):
        return f"{reverse('attendance:mes')}?mes={mes_escolhido:%Y-%m}"

    def get(self, request):
        escolhido = _mes_pedido(request)
        workers = self._workers(request, escolhido)
        if request.GET.get("exportar"):
            conteudo = mes.export_csv(workers, escolhido)
            resp = HttpResponse(conteudo, content_type="text/csv; charset=utf-8")
            resp["Content-Disposition"] = f'attachment; filename="ponto-{escolhido:%Y-%m}.csv"'
            return resp
        fechos = {
            f.worker_id: f
            for f in MonthClose.objects.filter(worker__in=workers, month=escolhido, reopened_at__isnull=True)
            .select_related("approved_by")
        }
        linhas = []
        for w in workers:
            dias, total = mes.month_rows(w, escolhido)
            falta = mes.pending_items(w, escolhido)
            linhas.append(
                {
                    "worker": w,
                    "dias": dias,
                    "dias_trabalhados": sum(1 for d in dias if d["entradas"]),
                    "total": total,
                    "falta": falta,
                    "pronto": not any(falta.values()),
                    "fecho": fechos.get(w.pk),
                }
            )
        atual = mes.month_start(timezone.localdate())
        return render(
            request,
            "manage/attendance/mes.html",
            {
                "mes": escolhido,
                "aqui": self._url(escolhido),
                "mes_anterior": mes.previous_month(escolhido),
                "mes_seguinte": mes.next_month(escolhido),
                "pode_aprovar": escolhido < atual,
                "pode_avancar": mes.next_month(escolhido) < atual,
                "linhas": linhas,
                "aprovados": sum(1 for l in linhas if l["fecho"]),
                "reaberturas": MonthClose.objects.filter(
                    worker__in=workers, month=escolhido, reopened_at__isnull=False
                ).select_related("worker", "reopened_by"),
            },
        )

    def post(self, request):
        escolhido = _mes_pedido(request)
        workers = self._workers(request, escolhido)
        acao = request.POST.get("acao")
        try:
            if acao == "aprovar_todos":
                aprovados, recusados = mes.approve_ready(workers=workers, month=escolhido, user=request.user)
                if aprovados:
                    messages.success(request, f"{len(aprovados)} trabalhador(es) aprovado(s)")
                if recusados:
                    messages.error(
                        request,
                        f"Ficaram {len(recusados)} por aprovar: " + "; ".join(m for _, m in recusados),
                    )
                if not aprovados and not recusados:
                    messages.success(request, "Todos os trabalhadores já estavam aprovados")
            else:
                worker = get_object_or_404(workers, pk=request.POST.get("worker"))
                if acao == "aprovar":
                    mes.approve_month(worker=worker, month=escolhido, user=request.user)
                    messages.success(request, f"Mês de {worker.full_name} aprovado")
                elif acao == "reabrir":
                    mes.reopen_month(
                        worker=worker, month=escolhido, user=request.user, reason=request.POST.get("motivo", "")
                    )
                    messages.success(request, f"Mês de {worker.full_name} reaberto")
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        return redirect(self._url(escolhido))
