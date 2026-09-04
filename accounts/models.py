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
    # PIN só para a vista staff (Fase 3); guardado com o hasher de passwords.
    staff_pin = models.CharField(max_length=128, null=True, blank=True, editable=False)
    pin_set_at = models.DateTimeField(null=True, blank=True, editable=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = "utilizador"
        verbose_name_plural = "utilizadores"

    def __str__(self):
        return self.get_full_name() or self.email

    def set_staff_pin(self, raw_pin):
        from django.contrib.auth.hashers import make_password
        from django.utils import timezone

        self.staff_pin = make_password(raw_pin)
        self.pin_set_at = timezone.now()
        self.save(update_fields=["staff_pin", "pin_set_at"])

    def check_staff_pin(self, raw_pin):
        from django.contrib.auth.hashers import check_password

        if not self.staff_pin:
            return False
        return check_password(raw_pin, self.staff_pin)

    @property
    def has_pin(self):
        return bool(self.staff_pin)

    @property
    def is_backoffice(self):
        """Perfis com acesso ao backoffice (a vista staff é para todos)."""
        return self.role in {self.Role.ADMIN, self.Role.MANAGER, self.Role.STOCK}
