"""Acesso das contas às casas (Fase 9). A linha de Membership da casa por
omissão segue `User.restaurant` e `User.role` (signal em signals.py); as
outras casas mudam-se só por aqui."""
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Membership, User


def perfil_na_casa(user, restaurant):
    """O perfil desta conta nesta casa, ou None se não tiver acesso."""
    if user.is_group_admin and user.organization_id == restaurant.organization_id:
        return User.Role.ADMIN
    return Membership.objects.filter(user=user, restaurant=restaurant).values_list("role", flat=True).first()


@transaction.atomic
def dar_acesso(user, restaurant, role):
    """Dá acesso a uma casa, ou muda o perfil nela."""
    if user.organization_id and user.organization_id != restaurant.organization_id:
        raise ValidationError("Esta conta é de outro grupo.")
    if user.restaurant_id in (None, restaurant.pk):
        user.restaurant, user.role = restaurant, role
        user.save()
    else:
        Membership.objects.update_or_create(user=user, restaurant=restaurant, defaults={"role": role})


@transaction.atomic
def tirar_acesso(user, restaurant):
    """Tira o acesso a uma casa. Se era a casa por omissão, passa a ser a
    primeira das que restam."""
    Membership.objects.filter(user=user, restaurant=restaurant).delete()
    if user.restaurant_id != restaurant.pk:
        return
    outra = user.memberships.select_related("restaurant").order_by("restaurant__name").first()
    user.restaurant = outra.restaurant if outra else None
    if outra:
        user.role = outra.role
    user.save()
