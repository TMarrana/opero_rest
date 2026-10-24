from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from core.mixins import ManagerRequiredMixin
from core.models import Restaurant
from core.utils import restaurant_scope
from workers.models import Worker

from .forms import AllowanceForm, DecisionForm, VacationRequestForm
from .models import Allowance, VacationRequest
from .services import allowance_for, balance, create_request, decide_request


def _scoped_requests(user):
    return restaurant_scope(
        user,
        VacationRequest.objects.select_related("worker", "decided_by", "absence_type"),
        field="worker__restaurant",
    )


def _restaurant(user):
    return user.restaurant or Restaurant.objects.first()


class VacationListView(ManagerRequiredMixin, TemplateView):
    """Pendentes primeiro, com aviso de sobreposição e de saldo; histórico
    filtrável por trabalhador e estado."""

    template_name = "manage/vacations/lista.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = _scoped_requests(self.request.user)
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
        ctx["workers"] = restaurant_scope(self.request.user, Worker.objects.filter(is_active=True))
        ctx["estados"] = [
            (v, l) for v, l in VacationRequest.Status.choices if v != VacationRequest.Status.PENDENTE
        ]
        ctx["form_decisao"] = DecisionForm()
        ctx["filtros"] = {"trabalhador": trabalhador, "estado": estado}
        return ctx


class VacationCreateView(ManagerRequiredMixin, View):
    """Ausência registada pelo gerente em nome do trabalhador: nasce
    aprovada, com o gerente como decisor (R-057)."""

    def get(self, request):
        form = VacationRequestForm(restaurant=_restaurant(request.user))
        return render(request, "manage/vacations/form.html", {"form": form})

    def post(self, request):
        form = VacationRequestForm(request.POST, restaurant=_restaurant(request.user))
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
        pedido = get_object_or_404(_scoped_requests(request.user), pk=pk)
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
        workers = restaurant_scope(request.user, Worker.objects.filter(is_active=True))
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
            restaurant_scope(request.user, Worker.objects.all()), pk=request.POST.get("worker")
        )
        saldo = Allowance.objects.filter(worker=worker, year=ano).first() or Allowance(worker=worker, year=ano)
        form = AllowanceForm(request.POST, instance=saldo, prefix=f"w{worker.pk}")
        if form.is_valid():
            form.save()
            messages.success(request, f"Saldo de {worker.full_name} guardado")
        else:
            messages.error(request, "Saldo não guardado: verifique os números.")
        return redirect(f"{request.path}?ano={ano}")
