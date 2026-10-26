"""
Mixins de autorização das views.

Verificação explícita por perfil — não confiar em esconder botões no
template (secção 2 do plano). O código de ponto do quiosque nunca cria
sessão (Fase 7), por isso aqui só chegam sessões de email e password.
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


class RoleRequiredMixin(LoginRequiredMixin):
    """Exige um dos perfis em allowed_roles."""

    allowed_roles: tuple = ()

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
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
    App do colaborador: qualquer utilizador autenticado por email e
    password, incluindo gerentes, que veem os próprios turnos e férias.
    Sem sessão, vai para o login de email (Fase 7).
    """

