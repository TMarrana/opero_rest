from django import forms
from django.contrib import messages
from django.views.generic import TemplateView

from core.mixins import RoleRequiredMixin


class _DemoForm(forms.Form):
    """Só para a página de componentes: um campo normal e um com erro."""

    nome = forms.CharField(
        label="Nome do artigo",
        help_text="Como aparece nas listagens e nos talões.",
        widget=forms.TextInput(attrs={"class": "campo-input", "placeholder": "Tomate chucha"}),
    )
    quantidade = forms.DecimalField(
        label="Quantidade",
        widget=forms.NumberInput(attrs={"class": "campo-input font-dados"}),
    )


class ComponentsView(RoleRequiredMixin, TemplateView):
    """
    Página de componentes do sistema de design — todos os elementos nos
    seus estados. Critério de aceitação da Fase 0.
    """

    template_name = "components.html"

    def dispatch(self, request, *args, **kwargs):
        from accounts.models import User

        self.allowed_roles = (User.Role.ADMIN, User.Role.MANAGER, User.Role.STOCK)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        form = _DemoForm(data={"nome": "", "quantidade": "abc"})
        form.is_valid()  # popula os erros para mostrar o estado de erro
        ctx["form_erro"] = form
        ctx["form_ok"] = _DemoForm()
        return ctx

    def post(self, request, *args, **kwargs):
        messages.success(request, "Entrada registada")
        return self.get(request, *args, **kwargs)
