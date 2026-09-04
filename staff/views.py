from django.views.generic import TemplateView

from core.mixins import StaffViewMixin


class StaffHomeView(StaffViewMixin, TemplateView):
    """Ecrã de ponto do colaborador. O botão de estado entra na Fase 3."""

    template_name = "staff/home.html"
