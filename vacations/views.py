import calendar
import datetime

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import TemplateView

from core import exports
from core.mixins import ManagerRequiredMixin
from core.utils import restaurant_scope
from workers.models import Worker

from .forms import AllowanceForm, DecisionForm, VacationRequestForm
from .models import AbsenceType, Allowance, BlockedPeriod, VacationRequest
from .services import (
    allowance_for,
    balance,
    cancel_by_manager,
    create_request,
    decide_request,
    holidays_between,
    manager_can_cancel,
)


def _scoped_requests(request):
    return restaurant_scope(
        request,
        VacationRequest.objects.select_related("worker", "decided_by", "absence_type"),
        field="worker__restaurant",
    )


class VacationListView(ManagerRequiredMixin, TemplateView):
    """Pendentes primeiro, com aviso de sobreposição e de saldo; histórico
    filtrável por trabalhador e estado."""

    template_name = "manage/vacations/lista.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = _scoped_requests(self.request)
        trabalhador = self.request.GET.get("trabalhador", "")
        estado = self.request.GET.get("estado", "")
        historico = qs.exclude(status=VacationRequest.Status.PENDENTE)
        if trabalhador:
            historico = historico.filter(worker_id=trabalhador)
        if estado:
            historico = historico.filter(status=estado)
        pendentes = list(qs.filter(status=VacationRequest.Status.PENDENTE).order_by("start_date"))
        for p in pendentes:
            # Um pedido acima do saldo não é bloqueado: em Portugal a
            # decisão é do gerente, que vê o aviso.
            if p.absence_type.deducts_balance:
                p.saldo = balance(p.worker, p.start_date.year)["disponiveis"]
                p.excede_saldo = p.days_taken > p.saldo
        ctx["pendentes"] = pendentes
        ctx["historico"] = historico[:100]
        ctx["workers"] = restaurant_scope(self.request, Worker.objects.filter(is_active=True))
        ctx["estados"] = [
            (v, l) for v, l in VacationRequest.Status.choices if v != VacationRequest.Status.PENDENTE
        ]
        ctx["form_decisao"] = DecisionForm()
        ctx["filtros"] = {"trabalhador": trabalhador, "estado": estado}
        return ctx


    def get(self, request, *args, **kwargs):
        formato = exports.formato_pedido(request)
        if formato:
            # Os pendentes e o histórico, com os filtros do histórico, sem o
            # limite de 100 do ecrã.
            qs = _scoped_requests(request).order_by("start_date", "worker__full_name")
            if request.GET.get("trabalhador"):
                qs = qs.filter(worker_id=request.GET["trabalhador"])
            if request.GET.get("estado"):
                qs = qs.filter(status=request.GET["estado"])
            return exports.responder(formato, [_tabela_ausencias(qs)], "ausencias")
        return super().get(request, *args, **kwargs)


def _tabela_ausencias(pedidos):
    return exports.Tabela(
        titulo="Ausências",
        colunas=["Trabalhador", "Tipo", "Início", "Fim", "Meio dia", "Dias", "Estado", "Pedido em", "Observação do pedido",
                 "Decidido por", "Decidido em", "Observação da decisão"],
        linhas=[
            [p.worker.full_name, p.absence_type.name, p.start_date, p.end_date, p.half_day, p.days_taken,
             p.get_status_display(), p.created_at, p.request_note, str(p.decided_by) if p.decided_by else "",
             p.decided_at, p.decision_note]
            for p in pedidos
        ],
        formatos=[exports.TEXTO, exports.TEXTO, exports.DATA, exports.DATA, exports.TEXTO, exports.NUMERO, exports.TEXTO,
                  exports.DATAHORA, exports.TEXTO, exports.TEXTO, exports.DATAHORA],
    )


class VacationCreateView(ManagerRequiredMixin, View):
    """Ausência registada pelo gerente em nome do trabalhador: nasce
    aprovada, com o gerente como decisor (R-057)."""

    def get(self, request):
        form = VacationRequestForm(restaurant=request.restaurant)
        return render(request, "manage/vacations/form.html", {"form": form})

    def post(self, request):
        form = VacationRequestForm(request.POST, restaurant=request.restaurant)
        if form.is_valid():
            try:
                create_request(
                    worker=form.cleaned_data["worker"],
                    absence_type=form.cleaned_data["absence_type"],
                    start_date=form.cleaned_data["start_date"],
                    end_date=form.cleaned_data["end_date"],
                    half_day=form.cleaned_data.get("half_day", False),
                    note=form.cleaned_data["request_note"],
                    created_by=request.user,
                )
                messages.success(request, "Ausência registada")
                return redirect("vacations:lista")
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
        return render(request, "manage/vacations/form.html", {"form": form})


class VacationDecideView(ManagerRequiredMixin, View):
    def post(self, request, pk, acao):
        pedido = get_object_or_404(_scoped_requests(request), pk=pk)
        form = DecisionForm(request.POST)
        form.is_valid()
        try:
            decide_request(
                request_obj=pedido,
                user=request.user,
                approve=(acao == "aprovar"),
                note=form.cleaned_data.get("decision_note", ""),
            )
            messages.success(request, "Pedido aprovado" if acao == "aprovar" else "Pedido recusado")
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        return redirect("vacations:lista")


class AllowanceListView(ManagerRequiredMixin, View):
    """Saldos de férias de um ano: dias do ano, transitados e quando
    caducam, usados e disponíveis. Editáveis linha a linha."""

    def _ano(self, request):
        try:
            return int(request.GET.get("ano") or request.POST.get("ano") or timezone.localdate().year)
        except ValueError:
            return timezone.localdate().year

    def get(self, request):
        ano = self._ano(request)
        workers = restaurant_scope(request, Worker.objects.filter(is_active=True))
        linhas = []
        for w in workers:
            form = AllowanceForm(instance=allowance_for(w, ano), prefix=f"w{w.pk}")
            for campo in form.fields.values():
                campo.widget.attrs["form"] = f"saldo-{w.pk}"
            linhas.append({"worker": w, "form": form, "saldo": balance(w, ano)})
        return render(
            request,
            "manage/vacations/saldos.html",
            {"ano": ano, "linhas": linhas, "ano_anterior": ano - 1, "ano_seguinte": ano + 1},
        )

    def post(self, request):
        ano = self._ano(request)
        worker = get_object_or_404(
            restaurant_scope(request, Worker.objects.all()), pk=request.POST.get("worker")
        )
        saldo = Allowance.objects.filter(worker=worker, year=ano).first() or Allowance(worker=worker, year=ano)
        form = AllowanceForm(request.POST, instance=saldo, prefix=f"w{worker.pk}")
        if form.is_valid():
            form.save()
            messages.success(request, f"Saldo de {worker.full_name} guardado")
        else:
            messages.error(request, "Saldo não guardado: verifique os números.")
        return redirect(f"{request.path}?ano={ano}")


def _mes(request):
    """Primeiro dia do mês pedido em ?mes=AAAA-MM; sem ele, o mês atual."""
    valor = request.GET.get("mes") or request.POST.get("mes") or ""
    try:
        ano, mes = (int(x) for x in valor.split("-"))
        return datetime.date(ano, mes, 1)
    except ValueError:
        return timezone.localdate().replace(day=1)


def _url_mes(dia):
    return f"{reverse('vacations:calendario')}?mes={dia:%Y-%m}"


def _ativas(restaurant, inicio, fim):
    """Ausências aprovadas e pendentes que tocam o período."""
    return VacationRequest.objects.filter(
        worker__restaurant=restaurant,
        status__in=[VacationRequest.Status.APROVADO, VacationRequest.Status.PENDENTE],
        start_date__lte=fim,
        end_date__gte=inicio,
    ).select_related("absence_type")


class CalendarView(ManagerRequiredMixin, View):
    """Calendário mensal das ausências da equipa: uma linha por
    trabalhador, uma coluna por dia. Aprovadas a cheio, pendentes
    tracejadas; fins de semana, feriados e períodos bloqueados à vista.
    Clicar numa célula abre o painel, como no planeador de turnos."""

    def get(self, request):
        restaurant = request.restaurant
        inicio = _mes(request)
        fim = inicio.replace(day=calendar.monthrange(inicio.year, inicio.month)[1])
        dias = [inicio + datetime.timedelta(days=i) for i in range(fim.day)]
        hoje = timezone.localdate()
        feriados = holidays_between(restaurant, inicio, fim)
        bloqueados = {}
        for b in BlockedPeriod.objects.filter(restaurant=restaurant, start__lte=fim, end__gte=inicio):
            for d in dias:
                if b.start <= d <= b.end:
                    bloqueados.setdefault(d, b.name)
        colunas = [
            {
                "dia": d,
                "fim_de_semana": d.weekday() >= 5,
                "feriado": feriados.get(d),
                "bloqueado": bloqueados.get(d),
                "hoje": d == hoje,
            }
            for d in dias
        ]

        por_trabalhador = {}
        for a in _ativas(restaurant, inicio, fim):
            por_trabalhador.setdefault(a.worker_id, []).append(a)
        fora = {d: 0 for d in dias}
        linhas = []
        for w in restaurant_scope(request, Worker.objects.filter(is_active=True)):
            ausencias = por_trabalhador.get(w.pk, [])
            celulas = []
            for col in colunas:
                do_dia = [a for a in ausencias if a.start_date <= col["dia"] <= a.end_date]
                # Uma aprovada tapa uma pendente no mesmo dia.
                do_dia.sort(key=lambda a: a.status != VacationRequest.Status.APROVADO)
                if do_dia and do_dia[0].status == VacationRequest.Status.APROVADO:
                    fora[col["dia"]] += 1
                ausencia = do_dia[0] if do_dia else None
                celulas.append(
                    {
                        **col,
                        "ausencia": ausencia,
                        "pendente": ausencia is not None and ausencia.status == VacationRequest.Status.PENDENTE,
                        # Duas letras do tipo, ou ½ num meio dia.
                        "texto": ("½" if ausencia.half_day else ausencia.absence_type.name[:2]) if ausencia else "",
                        "mais": len(do_dia) > 1,
                    }
                )
            linhas.append({"worker": w, "celulas": celulas, "saldo": balance(w, inicio.year)["disponiveis"]})
        anterior = (inicio - datetime.timedelta(days=1)).replace(day=1)
        return render(
            request,
            "manage/vacations/calendario.html",
            {
                "mes": inicio,
                "mes_anterior": anterior,
                "mes_seguinte": fim + datetime.timedelta(days=1),
                "colunas": colunas,
                "linhas": linhas,
                "fora": [fora[d] for d in dias],
                "tipos": AbsenceType.objects.filter(restaurant=restaurant, archived_at__isnull=True),
                "pendentes": _scoped_requests(request).filter(status=VacationRequest.Status.PENDENTE).count(),
            },
        )


class CalendarCellView(ManagerRequiredMixin, View):
    """Painel de uma célula do calendário (trabalhador × dia): marcar uma
    ausência a partir desse dia, aprovar ou recusar um pedido pendente, e
    cancelar uma ausência aprovada que ainda não acabou."""

    def _worker(self, request, pk):
        return get_object_or_404(restaurant_scope(request, Worker.objects.all()), pk=pk)

    def get(self, request, worker, dia):
        restaurant = request.restaurant
        worker = self._worker(request, worker)
        dia = parse_date(dia)
        ausencias = list(
            worker.vacation_requests.filter(
                status__in=[VacationRequest.Status.APROVADO, VacationRequest.Status.PENDENTE],
                start_date__lte=dia,
                end_date__gte=dia,
            ).select_related("absence_type", "decided_by")
        )
        hoje = timezone.localdate()
        for a in ausencias:
            a.cancelavel = manager_can_cancel(a, today=hoje)
        form = VacationRequestForm(
            restaurant=restaurant, with_worker=False, initial={"start_date": dia, "end_date": dia}
        )
        return render(
            request,
            "partials/vacations/celula.html",
            {
                "worker": worker,
                "dia": dia,
                "ausencias": ausencias,
                "form": form,
                "saldo": balance(worker, dia.year),
                "feriado": holidays_between(restaurant, dia, dia).get(dia),
            },
        )

    def post(self, request, worker, dia):
        restaurant = request.restaurant
        worker = self._worker(request, worker)
        dia = parse_date(dia)
        acao = request.POST.get("acao")
        try:
            if acao == "marcar":
                form = VacationRequestForm(request.POST, restaurant=restaurant, with_worker=False)
                if not form.is_valid():
                    erros = [e for lista in form.errors.values() for e in lista]
                    raise ValidationError(erros[0] if erros else "Verifique os campos da ausência.")
                create_request(
                    worker=worker,
                    absence_type=form.cleaned_data["absence_type"],
                    start_date=form.cleaned_data["start_date"],
                    end_date=form.cleaned_data["end_date"],
                    half_day=form.cleaned_data.get("half_day", False),
                    note=form.cleaned_data["request_note"],
                    created_by=request.user,
                )
                messages.success(request, f"Ausência de {worker.full_name} marcada")
            elif acao in ("aprovar", "recusar", "cancelar"):
                pedido = get_object_or_404(worker.vacation_requests, pk=request.POST.get("pedido"))
                if acao == "cancelar":
                    cancel_by_manager(request_obj=pedido, user=request.user)
                    messages.success(request, "Ausência cancelada")
                else:
                    decide_request(
                        request_obj=pedido,
                        user=request.user,
                        approve=acao == "aprovar",
                        note=request.POST.get("decision_note", ""),
                    )
                    messages.success(request, "Pedido aprovado" if acao == "aprovar" else "Pedido recusado")
            else:
                raise ValidationError("Ação inválida.")
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        return redirect(_url_mes(dia))
