from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView

from core.mixins import ManagerRequiredMixin
from core.models import Restaurant
from core.utils import restaurant_scope
from workers.models import Worker

from .forms import DecisionForm, VacationRequestForm
from .models import VacationRequest
from .services import decide_request


def _scoped_requests(user):
    return restaurant_scope(
        user,
        VacationRequest.objects.select_related("worker", "decided_by"),
        field="worker__restaurant",
    )


class VacationListView(ManagerRequiredMixin, TemplateView):
    """Pendentes primeiro, com aviso de sobreposição; histórico filtrável
    por trabalhador e estado."""

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
        ctx["pendentes"] = qs.filter(status=VacationRequest.Status.PENDENTE).order_by("start_date")
        ctx["historico"] = historico[:100]
        ctx["workers"] = restaurant_scope(self.request.user, Worker.objects.filter(is_active=True))
        ctx["estados"] = [
            (v, l) for v, l in VacationRequest.Status.choices if v != VacationRequest.Status.PENDENTE
        ]
        ctx["form_decisao"] = DecisionForm()
        ctx["filtros"] = {"trabalhador": trabalhador, "estado": estado}
        return ctx


class VacationCreateView(ManagerRequiredMixin, View):
    """Pedido registado pelo gerente em nome do trabalhador. Na Fase 3 o
    colaborador passa a pedir diretamente na vista staff."""

    def get(self, request):
        restaurant = request.user.restaurant or Restaurant.objects.first()
        form = VacationRequestForm(restaurant=restaurant)
        return render(request, "manage/vacations/form.html", {"form": form})

    def post(self, request):
        restaurant = request.user.restaurant or Restaurant.objects.first()
        form = VacationRequestForm(request.POST, restaurant=restaurant)
        if not form.is_valid():
            return render(request, "manage/vacations/form.html", {"form": form})
        form.save()
        messages.success(request, "Pedido registado")
        return redirect("vacations:lista")


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
