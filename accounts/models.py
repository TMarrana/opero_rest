from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import UserManager


class User(AbstractUser):
    """
    Utilizador custom desde a primeira migração (secção 2 do plano).
    Email como identificador; sem username.
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrador"
        MANAGER = "MANAGER", "Gerente"
        STOCK = "STOCK", "Responsável de stock"
        STAFF = "STAFF", "Colaborador"

    username = None
    email = models.EmailField("email", unique=True)
    # Casa e perfil por omissão (Fase 9). O acesso de verdade está em
    # Membership, uma linha por casa; o signal mantém a linha da casa por
    # omissão igual a estes dois campos.
    restaurant = models.ForeignKey(
        "core.Restaurant",
        verbose_name="restaurante",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
    )
    role = models.CharField("perfil", max_length=10, choices=Role.choices, default=Role.STAFF)
    organization = models.ForeignKey(
        "core.Organization",
        verbose_name="grupo",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
    )
    # Admin do grupo: perfil de Administrador em todas as casas ativas do
    # grupo, sem precisar de uma Membership em cada uma (secção 7).
    is_group_admin = models.BooleanField("admin do grupo", default=False)
    # Conta criada ou reposta pelo gerente com uma password provisória: o
    # titular tem de a mudar antes de fazer outra coisa (Fase 7).
    must_change_password = models.BooleanField("tem de mudar a password", default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = "utilizador"
        verbose_name_plural = "utilizadores"

    def __str__(self):
        return self.get_full_name() or self.email

    def save(self, *args, **kwargs):
        if self.organization_id is None and self.restaurant_id is not None:
            from core.models import Restaurant

            self.organization_id = Restaurant.objects.values_list("organization_id", flat=True).get(
                pk=self.restaurant_id
            )
        super().save(*args, **kwargs)

    def casas(self):
        """{restaurante: perfil} das casas ativas a que esta conta tem
        acesso, por ordem do nome (Fase 9)."""
        from core.models import Restaurant

        if self.is_group_admin and self.organization_id:
            qs = Restaurant.objects.filter(organization_id=self.organization_id, is_active=True)
            return {r: self.Role.ADMIN for r in qs}
        linhas = self.memberships.filter(restaurant__is_active=True).select_related("restaurant")
        return {m.restaurant: m.role for m in sorted(linhas, key=lambda m: m.restaurant.name)}

    @property
    def is_backoffice(self):
        """Tem acesso ao backoffice em pelo menos uma casa (a vista staff é
        para todos)."""
        return any(role in BACKOFFICE_ROLES for role in self.casas().values())


BACKOFFICE_ROLES = {User.Role.ADMIN, User.Role.MANAGER, User.Role.STOCK}


class Membership(models.Model):
    """Acesso de uma conta a uma casa, com o perfil nessa casa (Fase 9): a
    mesma pessoa pode ser gerente numa casa e não ter acesso a outra."""

    user = models.ForeignKey(User, verbose_name="utilizador", on_delete=models.CASCADE, related_name="memberships")
    restaurant = models.ForeignKey(
        "core.Restaurant", verbose_name="restaurante", on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField("perfil", max_length=10, choices=User.Role.choices)
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "acesso a casa"
        verbose_name_plural = "acessos a casas"
        constraints = [
            models.UniqueConstraint(fields=["user", "restaurant"], name="um_acesso_por_casa"),
        ]

    def __str__(self):
        return f"{self.user} · {self.restaurant} · {self.get_role_display()}"
