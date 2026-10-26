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
    restaurant = models.ForeignKey(
        "core.Restaurant",
        verbose_name="restaurante",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
    )
    role = models.CharField("perfil", max_length=10, choices=Role.choices, default=Role.STAFF)
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

    @property
    def is_backoffice(self):
        """Perfis com acesso ao backoffice (a vista staff é para todos)."""
        return self.role in {self.Role.ADMIN, self.Role.MANAGER, self.Role.STOCK}
