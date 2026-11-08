import hashlib

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError

from core.throttle import Limite

# 10 falhas do mesmo email e do mesmo IP bloqueiam o login durante 15
# minutos. Com o IP na chave, quem erra a password de outro sítio não
# bloqueia o dono da conta (decidido pelo TM a 2026-11-08).
LIMITE_LOGIN = Limite("login-falhas", 10, 900)


def _ip(request):
    """O IP do cliente. Atrás do proxy do alojamento é o último do
    X-Forwarded-For (o que o proxy acrescentou); os anteriores vêm do
    cliente e podiam mudar a cada tentativa."""
    if request is None:
        return ""
    encaminhado = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if encaminhado:
        return encaminhado.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR", "")


def _chave(email, request):
    """Hash do email normalizado e do IP: a cache não guarda emails nem IPs."""
    return hashlib.sha256(f"{email.strip().lower()}|{_ip(request)}".encode()).hexdigest()


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
        email = self.fields["username"]
        email.label = "Email"
        # No telemóvel: teclado de email, sem maiúscula nem corretor; «username»
        # é o que os gestores de palavras-passe procuram. Os atributos que o
        # Django já pôs (autofocus, maxlength) passam para o widget novo.
        email.widget = forms.EmailInput(
            attrs={
                **email.widget.attrs,
                "class": "campo-input",
                "autocomplete": "username",
                "inputmode": "email",
                "autocapitalize": "none",
                "spellcheck": "false",
                "placeholder": "nome@restaurante.pt",
            }
        )
        self.fields["password"].label = "Palavra-passe"
        self.fields["password"].widget.attrs.update(
            {"class": "campo-input", "autocomplete": "current-password"}
        )

    def clean(self):
        email = self.cleaned_data.get("username")
        if not email:
            return super().clean()
        chave = _chave(email, self.request)
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
