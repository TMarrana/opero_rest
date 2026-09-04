from django.views.generic import TemplateView

from core.mixins import RoleRequiredMixin


class DashboardView(RoleRequiredMixin, TemplateView):
    """Home do backoffice. Conteúdo agregado entra na Fase 4."""

    template_name = "manage/dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        from accounts.models import User

        self.allowed_roles = (User.Role.ADMIN, User.Role.MANAGER, User.Role.STOCK)
        return super().dispatch(request, *args, **kwargs)
