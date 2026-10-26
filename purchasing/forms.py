from django import forms
from django.utils import timezone

from .models import DIAS_SEMANA, Supplier

_INPUT = {"class": "campo-input"}
_DADOS = {"class": "campo-input font-dados"}


class SupplierForm(forms.ModelForm):
    delivery_days = forms.MultipleChoiceField(
        label="Dias de entrega",
        choices=DIAS_SEMANA,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Os dias em que costuma entregar. Serve de lembrete na lista de compras.",
    )

    class Meta:
        model = Supplier
        fields = ["name", "nif", "contact_name", "phone", "email", "delivery_days", "notes"]
        widgets = {
            "name": forms.TextInput(attrs=_INPUT),
            "nif": forms.TextInput(attrs={**_DADOS, "inputmode": "numeric"}),
            "contact_name": forms.TextInput(attrs=_INPUT),
            "phone": forms.TextInput(attrs={**_DADOS, "inputmode": "tel"}),
            "email": forms.EmailInput(attrs=_INPUT),
            "notes": forms.Textarea(attrs={**_INPUT, "rows": 3}),
        }
        help_texts = {"notes": "Encomenda mínima, hora limite para encomendar, condições de pagamento."}

    def __init__(self, *args, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        if self.instance.pk:
            self.initial["delivery_days"] = [d for d in self.instance.delivery_days.split(",") if d]

    def clean_name(self):
        nome = self.cleaned_data["name"].strip()
        repetido = Supplier.objects.filter(organization=self.organization, name__iexact=nome).exclude(pk=self.instance.pk)
        if repetido.exists():
            raise forms.ValidationError("Já existe um fornecedor com este nome no grupo.")
        return nome

    def clean_delivery_days(self):
        return ",".join(sorted(self.cleaned_data["delivery_days"]))


class ReceiptHeaderForm(forms.Form):
    document_number = forms.CharField(
        label="Número da fatura ou guia",
        max_length=60,
        widget=forms.TextInput(attrs=_DADOS),
        help_text="Como vem no papel que acompanha a mercadoria.",
    )
    document_date = forms.DateField(
        label="Data da fatura ou guia",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={**_DADOS, "type": "date"}, format="%Y-%m-%d"),
    )
    notes = forms.CharField(
        label="Observações", max_length=300, required=False, widget=forms.TextInput(attrs=_INPUT)
    )
