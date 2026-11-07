import hashlib

from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError

from core.throttle import Limite

# 10 falhas por email bloqueiam o login durante 15 minutos.
LIMITE_LOGIN = Limite("login-falhas", 10, 900)


def _chave_email(email):
    """Hash do email normalizado: a cache não guarda emails nem chaves com espaços."""
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


class LoginForm(AuthenticationForm):
    """Login do backoffice: email + password. PIN é outro caminho (Fase 3)."""

    error_messages = {
        "invalid_login": "Email ou palavra-passe errados. Verifique e tente de novo.",
        "inactive": "Esta conta está desativada. Fale com o gerente.",
        "bloqueado": (
            "Demasiadas tentativas. Espere 15 minutos ou peça ao gerente "
            "uma palavra-passe provisória."
        ),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email"
        self.fields["username"].widget.attrs.update(
            {"class": "campo-input", "autocomplete": "email", "placeholder": "nome@restaurante.pt"}
        )
        self.fields["password"].label = "Palavra-passe"
        self.fields["password"].widget.attrs.update(
            {"class": "campo-input", "autocomplete": "current-password"}
        )

    def clean(self):
        email = self.cleaned_data.get("username")
        if not email:
            return super().clean()
        chave = _chave_email(email)
        if LIMITE_LOGIN.bloqueado(chave):
            raise ValidationError(self.error_messages["bloqueado"], code="bloqueado")
        try:
            dados = super().clean()
        except ValidationError:
            LIMITE_LOGIN.falhou(chave)
            raise
        if self.user_cache is not None:
            LIMITE_LOGIN.limpar(chave)
        return dados
