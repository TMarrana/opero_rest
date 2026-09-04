from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User

# Grupo Django correspondente a cada perfil. A autorização nas views usa
# os mixins de core/mixins.py; os grupos mantêm o admin e futuras
# permissões por objeto coerentes com o campo role.
ROLE_GROUP = {
    User.Role.ADMIN: "Administrador",
    User.Role.MANAGER: "Gerente",
    User.Role.STOCK: "Responsável de stock",
    User.Role.STAFF: "Colaborador",
}


@receiver(post_save, sender=User)
def sync_role_group(sender, instance, **kwargs):
    wanted = ROLE_GROUP.get(instance.role)
    if not wanted:
        return
    instance.groups.remove(*instance.groups.filter(name__in=set(ROLE_GROUP.values()) - {wanted}))
    group, _ = Group.objects.get_or_create(name=wanted)
    instance.groups.add(group)
