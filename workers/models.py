from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class Worker(TimeStampedModel):
    """Pessoa que trabalha no restaurante. Pode ou não ter conta (User)."""

    restaurant = models.ForeignKey(
        "core.Restaurant", verbose_name="restaurante", on_delete=models.CASCADE, related_name="workers"
    )
    full_name = models.CharField("nome completo", max_length=150)
    contact = models.CharField("contacto", max_length=120, blank=True)
    job_title = models.CharField("função", max_length=80, blank=True)
    is_active = models.BooleanField("ativo", default=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="utilizador",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="worker",
    )
    start_date = models.DateField("data de início", null=True, blank=True)
    notes = models.TextField("notas", blank=True)
    # Código de ponto do tablet partilhado (Fase 7), guardado com o hasher
    # de passwords. É da ficha e não da conta: quem não tem conta pica na
    # mesma. Nunca abre uma sessão.
    kiosk_code = models.CharField(max_length=128, null=True, blank=True, editable=False)
    code_set_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "trabalhador"
        verbose_name_plural = "trabalhadores"
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name

    def set_kiosk_code(self, raw_code):
        from django.contrib.auth.hashers import make_password
        from django.utils import timezone

        self.kiosk_code = make_password(raw_code)
        self.code_set_at = timezone.now()
        self.save(update_fields=["kiosk_code", "code_set_at", "updated_at"])

    def check_kiosk_code(self, raw_code):
        from django.contrib.auth.hashers import check_password

        if not self.kiosk_code:
            return False
        return check_password(raw_code, self.kiosk_code)

    @property
    def has_code(self):
        return bool(self.kiosk_code)

    @property
    def open_entry(self):
        """O turno em curso. Uma entrada sem saída que passou do limite
        está por resolver e já não é o turno em curso (Fase 5)."""
        entry = self.time_entries.filter(check_out__isnull=True, missing_exit=False).first()
        if entry is None or entry.is_unresolved():
            return None
        return entry
