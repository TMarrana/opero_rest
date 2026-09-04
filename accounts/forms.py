from django.contrib.auth.forms import AuthenticationForm


class LoginForm(AuthenticationForm):
    """Login do backoffice: email + password. PIN é outro caminho (Fase 3)."""

    error_messages = {
        "invalid_login": "Email ou palavra-passe errados. Verifique e tente de novo.",
        "inactive": "Esta conta está desativada. Fale com o gerente.",
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
