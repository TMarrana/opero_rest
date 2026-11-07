"""
Mixins de autorização das views.

Verificação explícita por perfil — não confiar em esconder botões no
template (secção 2 do plano). O código de ponto do quiosque nunca cria
sessão (Fase 7), por isso aqui só chegam sessões de email e password.
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

from core import permissions


class RoleRequiredMixin(LoginRequiredMixin):
    """Exige um dos perfis em allowed_roles, na casa ativa do pedido
    (Fase 9, `core.middleware.ActiveRestaurantMiddleware`). Sem acesso a
    nenhuma casa, o perfil é None e o pedido é recusado."""

    allowed_roles: tuple | frozenset = ()

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if self.allowed_roles and request.role not in self.allowed_roles:
                raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin(RoleRequiredMixin):
    """Só Admin: gestão de utilizadores e configuração da casa."""

    allowed_roles = permissions.ADMIN


class ManagerRequiredMixin(RoleRequiredMixin):
    """Admin ou Gerente: trabalhadores, ponto da equipa, férias."""

    allowed_roles = permissions.PESSOAS


class StockRequiredMixin(RoleRequiredMixin):
    """
    Admin, Gerente ou Responsável de stock.
    ⚠ Pressuposto a validar com AT (secção 7): o gerente pode criar
    artigos e registar movimentos. Restringir depois é retirar
    User.Role.MANAGER de `core.permissions.STOCK`.
    """

    allowed_roles = permissions.STOCK


class StaffViewMixin(LoginRequiredMixin):
    """
    App do colaborador: qualquer utilizador autenticado por email e
    password, incluindo gerentes, que veem os próprios turnos e férias.
    Sem sessão, vai para o login de email (Fase 7).
    """


class GroupAdminRequiredMixin(LoginRequiredMixin):
    """Só o Admin do grupo: casas, acessos e o painel do grupo (Fase 9)."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not (request.user.is_group_admin and request.user.organization_id):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
