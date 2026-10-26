from django import forms
from django.contrib.auth import get_user_model

from .models import Worker

_INPUT = {"class": "campo-input"}
User = get_user_model()


class WorkerForm(forms.ModelForm):
    class Meta:
        model = Worker
        fields = ["full_name", "job_title", "contact", "start_date", "user", "is_active", "notes"]
        widgets = {
            "full_name": forms.TextInput(attrs=_INPUT),
            "job_title": forms.TextInput(attrs={**_INPUT, "placeholder": "Ex.: cozinha, sala, copa"}),
            "contact": forms.TextInput(attrs={**_INPUT, "placeholder": "Telefone ou email"}),
            "start_date": forms.DateInput(attrs={**_INPUT, "class": "campo-input font-dados", "type": "date"}, format="%Y-%m-%d"),
            "user": forms.Select(attrs=_INPUT),
            "notes": forms.Textarea(attrs={**_INPUT, "rows": 3}),
        }
        labels = {"is_active": "Trabalhador ativo", "user": "Conta de acesso (opcional)"}
        help_texts = {
            "user": "Liga este trabalhador a uma conta que já existe. Para criar uma conta nova, use «Conta da app»."
        }

    def __init__(self, *args, restaurant=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = User.objects.filter(is_active=True)
        if restaurant is not None:
            qs = qs.filter(restaurant=restaurant)
        livres = qs.filter(worker__isnull=True)
        if self.instance.pk and self.instance.user_id:
            livres = livres | qs.filter(pk=self.instance.user_id)
        self.fields["user"].queryset = livres.distinct()


class KioskCodeForm(forms.Form):
    """Código de ponto do tablet partilhado (Fase 7)."""

    codigo = forms.RegexField(
        regex=r"^\d{4,6}$",
        label="Código de ponto",
        error_messages={"invalid": "O código são 4 a 6 algarismos."},
        widget=forms.PasswordInput(
            attrs={**_INPUT, "class": "campo-input font-dados", "inputmode": "numeric", "autocomplete": "off"}
        ),
    )


def roles_que_gere(user):
    """Perfis das contas que este utilizador pode criar e gerir (secção 7):
    o admin gere todas; o gerente, só as de Colaborador e Resp. stock."""
    if user.role == User.Role.ADMIN:
        return list(User.Role)
    if user.role == User.Role.MANAGER:
        return [User.Role.STAFF, User.Role.STOCK]
    return []


class _RoleField(forms.ChoiceField):
    def __init__(self, gestor, **kwargs):
        super().__init__(
            label="Perfil",
            choices=[(r.value, r.label) for r in roles_que_gere(gestor)],
            widget=forms.Select(attrs=_INPUT),
            **kwargs,
        )


class AccountCreateForm(forms.Form):
    email = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={**_INPUT, "autocomplete": "off"}))

    def __init__(self, *args, gestor, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"] = _RoleField(gestor, initial=User.Role.STAFF)

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"]).lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "Já existe uma conta com este email. Para a ligar a este trabalhador, escolha-a em "
                "«Conta de acesso» no formulário do trabalhador."
            )
        return email


class AccountRoleForm(forms.Form):
    def __init__(self, *args, gestor, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"] = _RoleField(gestor)
