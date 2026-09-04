"""
Mixins de autorização das views.

Verificação explícita por perfil — não confiar em esconder botões no
template (secção 2 do plano). A fronteira PIN/backoffice (secção 7)
também se aplica aqui: uma sessão criada por PIN nunca passa num mixin
de backoffice, mesmo que o titular seja gerente.
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.urls import reverse_lazy

# Marcador na sessão de que a autenticação foi feita por PIN (Fase 3).
PIN_SESSION_KEY = "auth_via_pin"


class RoleRequiredMixin(LoginRequiredMixin):
    """Exige um dos perfis em allowed_roles e sessão de email+password."""

    allowed_roles: tuple = ()

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if request.session.get(PIN_SESSION_KEY):
                raise PermissionDenied("Sessão por PIN não dá acesso ao backoffice.")
            if self.allowed_roles and request.user.role not in self.allowed_roles:
                raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin(RoleRequiredMixin):
    """Só Admin: gestão de utilizadores e configuração do restaurante."""

    def dispatch(self, request, *args, **kwargs):
        from accounts.models import User

        self.allowed_roles = (User.Role.ADMIN,)
        return super().dispatch(request, *args, **kwargs)


class ManagerRequiredMixin(RoleRequiredMixin):
    """Admin ou Gerente: trabalhadores, ponto da equipa, férias."""

    def dispatch(self, request, *args, **kwargs):
        from accounts.models import User

        self.allowed_roles = (User.Role.ADMIN, User.Role.MANAGER)
        return super().dispatch(request, *args, **kwargs)


class StockRequiredMixin(RoleRequiredMixin):
    """
    Admin, Gerente ou Responsável de stock.
    ⚠ Pressuposto a validar com AT (secção 7): o gerente pode criar
    artigos e registar movimentos. Restringir depois é retirar
    User.Role.MANAGER desta lista.
    """

    def dispatch(self, request, *args, **kwargs):
        from accounts.models import User

        self.allowed_roles = (User.Role.ADMIN, User.Role.MANAGER, User.Role.STOCK)
        return super().dispatch(request, *args, **kwargs)


class StaffViewMixin(LoginRequiredMixin):
    """
    Vista staff: qualquer utilizador autenticado, incluindo por PIN.

    Sem sessão, reencaminha para o login por PIN e não para o do
    backoffice: a PWA arranca em /equipa/ e quem a abre está a marcar
    ponto, não a entrar na gestão.
    """

    login_url = reverse_lazy("staff:pin_login")
