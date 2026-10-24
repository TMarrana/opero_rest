from django.db.models import F
from django.views.generic import TemplateView

from attendance.models import CorrectionRequest, TimeEntry
from core.mixins import RoleRequiredMixin
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
        user = self.request.user

        itens_baixos = (
            restaurant_scope(user, Item.objects.filter(is_active=True))
            .filter(current_stock__lte=F("minimum_stock"))
            .select_related("category")
        )
        ctx["stock_baixo"] = itens_baixos[:6]
        ctx["contador_baixo"] = itens_baixos.count()

        ctx["ultimos_movimentos"] = restaurant_scope(
            user,
            StockMovement.objects.select_related("item", "created_by"),
            field="item__restaurant",
        )[:5]

        # As áreas de pessoas só aparecem a quem as pode abrir (matriz da secção 7).
        ctx["ve_pessoas"] = user.role in ("ADMIN", "MANAGER") or user.restaurant_id is None
        if ctx["ve_pessoas"]:
            ctx["ferias_pendentes"] = restaurant_scope(
                user,
                VacationRequest.objects.filter(status=VacationRequest.Status.PENDENTE)
                .select_related("worker")
                .order_by("start_date"),
                field="worker__restaurant",
            )[:6]
            entradas = restaurant_scope(user, TimeEntry.objects.all(), field="worker__restaurant")
            ctx["em_turno"] = (
                entradas.filter(check_out__isnull=True).resolved().select_related("worker").order_by("check_in")
            )
            ctx["por_resolver"] = entradas.unresolved().count()
            ctx["pedidos_correcao"] = restaurant_scope(
                user,
                CorrectionRequest.objects.filter(status=CorrectionRequest.Status.PENDENTE),
                field="worker__restaurant",
            ).count()
        return ctx
