from django import forms
from django.contrib.auth import get_user_model
from django.utils.text import capfirst

from core.models import Restaurant

from .formatos import normalizar_contacto
from .models import Worker

_INPUT = {"class": "campo-input"}
User = get_user_model()


class WorkerForm(forms.ModelForm):
    class Meta:
        model = Worker
        fields = ["full_name", "job_title", "contact", "start_date", "is_active", "notes", "other_restaurants"]
        widgets = {
            "full_name": forms.TextInput(attrs=_INPUT),
            "job_title": forms.TextInput(attrs={**_INPUT, "placeholder": "Ex.: cozinha, sala, copa"}),
            "contact": forms.TextInput(attrs={**_INPUT, "placeholder": "Telefone ou email"}),
            "start_date": forms.DateInput(attrs={**_INPUT, "class": "campo-input font-dados", "type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={**_INPUT, "rows": 3}),
            "other_restaurants": forms.CheckboxSelectMultiple,
        }
        labels = {"is_active": "Trabalhador ativo"}
        help_texts = {
            "other_restaurants": "Pica e tem turnos nestas casas. A ficha, as férias e o fecho do mês ficam nesta, "
            "que é a casa principal.",
        }

    # Obrigatórios na ficha (decidido a 2026-11-04). No modelo continuam
    # opcionais, por causa das fichas antigas.
    OBRIGATORIOS = {
        "job_title": "Indique a função.",
        "contact": "Indique um contacto: telefone ou email.",
        "start_date": "Indique a data de início.",
    }

    def __init__(self, *args, restaurant=None, **kwargs):
        super().__init__(*args, **kwargs)
        # A conta da app cria-se em «Conta da app»: cada trabalhador tem a
        # sua, com um email que nenhuma outra conta usa.
        for nome, erro in self.OBRIGATORIOS.items():
            self.fields[nome].required = True
            self.fields[nome].error_messages["required"] = erro
        # As outras casas do mesmo grupo (Fase 9). Num grupo de uma só casa,
        # o campo não aparece.
        outras = Restaurant.objects.none()
        if restaurant is not None:
            outras = Restaurant.objects.filter(
                organization_id=restaurant.organization_id, is_active=True
            ).exclude(pk=restaurant.pk)
        if self.instance.pk:
            outras = outras | self.instance.other_restaurants.all()
        self.fields["other_restaurants"].queryset = outras.distinct().order_by("name")
        if not self.fields["other_restaurants"].queryset.exists():
            del self.fields["other_restaurants"]

    def clean_job_title(self):
        """«copeiro» fica «Copeiro», ao lado de «Sala» e «Cozinha»."""
        return capfirst(self.cleaned_data["job_title"].strip())

    def clean_contact(self):
        """Os telefones portugueses ficam todos «+351 965 852 489»."""
        return normalizar_contacto(self.cleaned_data["contact"])


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


def roles_que_gere(role):
    """Perfis das contas que quem tem este perfil na casa pode criar e gerir
    (secção 7): o admin gere todas; o gerente, só as de Colaborador e
    Resp. stock."""
    if role == User.Role.ADMIN:
        return list(User.Role)
    if role == User.Role.MANAGER:
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
                "Já existe uma conta com este email. Cada conta é de uma só pessoa: use outro email."
            )
        return email


class AccountRoleForm(forms.Form):
    def __init__(self, *args, gestor, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"] = _RoleField(gestor)
