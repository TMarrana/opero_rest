from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import F
from django.shortcuts import redirect
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from accounts.models import BACKOFFICE_ROLES
from attendance.models import CorrectionRequest, TimeEntry
from core.middleware import SESSION_KEY
from core.mixins import GroupAdminRequiredMixin, RoleRequiredMixin
from core.utils import restaurant_scope
from inventory.models import Item, StockMovement
from vacations.models import VacationRequest


class DashboardView(RoleRequiredMixin, TemplateView):
    """Dashboard do gerente (Fase 4): sem gráficos sofisticados — os
    quatro sinais do docx, cada um a um clique do seu módulo."""

    template_name = "manage/dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        from accounts.models import User

        self.allowed_roles = (User.Role.ADMIN, User.Role.MANAGER, User.Role.STOCK)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        request = self.request

        itens_baixos = (
            restaurant_scope(request, Item.objects.filter(is_active=True))
            .filter(current_stock__lte=F("minimum_stock"))
            .select_related("category")
        )
        ctx["stock_baixo"] = itens_baixos[:6]
        ctx["contador_baixo"] = itens_baixos.count()

        ctx["ultimos_movimentos"] = restaurant_scope(
            request,
            StockMovement.objects.select_related("item", "created_by"),
            field="item__restaurant",
        )[:5]

        # As áreas de pessoas só aparecem a quem as pode abrir (matriz da secção 7).
        ctx["ve_pessoas"] = request.role in ("ADMIN", "MANAGER")
        if ctx["ve_pessoas"]:
            ctx["ferias_pendentes"] = restaurant_scope(
                request,
                VacationRequest.objects.filter(status=VacationRequest.Status.PENDENTE)
                .select_related("worker")
                .order_by("start_date"),
                field="worker__restaurant",
            )[:6]
            entradas = restaurant_scope(request, TimeEntry.objects.all(), field="worker__restaurant")
            ctx["em_turno"] = (
                entradas.filter(check_out__isnull=True).resolved().select_related("worker").order_by("check_in")
            )
            ctx["por_resolver"] = entradas.unresolved().count()
            # Aviso de mês por fechar: a partir do dia 1, até todos os
            # trabalhadores ativos terem o mês anterior aprovado.
            from attendance.models import MonthClose
            from attendance.month import previous_month
            from workers.models import Worker

            anterior = previous_month(timezone.localdate())
            ativos = restaurant_scope(request, Worker.objects.filter(is_active=True))
            aprovados = MonthClose.objects.filter(
                worker__in=ativos, month=anterior, reopened_at__isnull=True
            ).count()
            ctx["mes_por_fechar"] = anterior
            ctx["por_aprovar"] = ativos.count() - aprovados
            ctx["pedidos_correcao"] = restaurant_scope(
                request,
                CorrectionRequest.objects.filter(status=CorrectionRequest.Status.PENDENTE),
                field="worker__restaurant",
            ).count()
        return ctx


class SwitchRestaurantView(LoginRequiredMixin, View):
    """Muda a casa ativa (Fase 9). Volta ao dashboard e não à página onde
    estava, porque essa página era da outra casa."""

    def post(self, request):
        casa = next((r for r in request.casas if str(r.pk) == request.POST.get("casa")), None)
        if casa is None:
            messages.error(request, "Não tem acesso a essa casa.")
        else:
            request.session[SESSION_KEY] = casa.pk
        if casa is not None and request.casas[casa] not in BACKOFFICE_ROLES:
            return redirect("staff:home")
        return redirect("dashboard:home")


def _sinais(restaurant):
    """Os sinais do dashboard de uma casa, em números (painel do grupo)."""
    from attendance.models import MonthClose
    from attendance.month import previous_month
    from workers.models import Worker

    entradas = TimeEntry.objects.filter(worker__restaurant=restaurant)
    ativos = Worker.objects.filter(restaurant=restaurant, is_active=True)
    anterior = previous_month(timezone.localdate())
    aprovados = MonthClose.objects.filter(worker__in=ativos, month=anterior, reopened_at__isnull=True).count()
    return {
        "casa": restaurant,
        "stock_baixo": Item.objects.filter(restaurant=restaurant, is_active=True, current_stock__lte=F("minimum_stock")).count(),
        "em_turno": entradas.filter(check_out__isnull=True).resolved().count(),
        "por_resolver": entradas.unresolved().count(),
        "ferias_pendentes": VacationRequest.objects.filter(
            worker__restaurant=restaurant, status=VacationRequest.Status.PENDENTE
        ).count(),
        "correcoes_pendentes": CorrectionRequest.objects.filter(
            worker__restaurant=restaurant, status=CorrectionRequest.Status.PENDENTE
        ).count(),
        "por_aprovar": ativos.count() - aprovados,
    }


class GroupDashboardView(GroupAdminRequiredMixin, TemplateView):
    """Painel do grupo (Fase 9): uma linha por casa, com os mesmos sinais do
    dashboard. Só o Admin do grupo vê as casas lado a lado (secção 7)."""

    template_name = "manage/grupo/painel.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from attendance.month import previous_month

        ctx["linhas"] = [_sinais(casa) for casa in self.request.casas]
        ctx["mes_por_fechar"] = previous_month(timezone.localdate())
        return ctx
