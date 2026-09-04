from django import forms
from django.utils import timezone

from .models import Category, Item, StockMovement

_INPUT = {"class": "campo-input"}
_INPUT_DADOS = {"class": "campo-input font-dados"}


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name"]
        widgets = {"name": forms.TextInput(attrs={**_INPUT, "placeholder": "Ex.: Congelados"})}


class ItemForm(forms.ModelForm):
    """Sem current_stock (invariante 1): o stock inicial entra por movimento."""

    class Meta:
        model = Item
        fields = ["name", "category", "unit", "minimum_stock", "reference_cost", "is_active", "notes"]
        widgets = {
            "name": forms.TextInput(attrs=_INPUT),
            "category": forms.Select(attrs=_INPUT),
            "unit": forms.Select(attrs=_INPUT),
            "minimum_stock": forms.NumberInput(attrs={**_INPUT_DADOS, "step": "0.001", "min": "0"}),
            "reference_cost": forms.NumberInput(attrs={**_INPUT_DADOS, "step": "0.01", "min": "0"}),
            "notes": forms.Textarea(attrs={**_INPUT, "rows": 3}),
        }
        labels = {"is_active": "Artigo ativo"}
        help_texts = {
            "minimum_stock": "Abaixo ou igual a este valor, o artigo fica assinalado a stock baixo.",
        }

    def __init__(self, *args, restaurant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if restaurant is not None:
            self.fields["category"].queryset = Category.objects.filter(restaurant=restaurant)


class MovementForm(forms.Form):
    movement_type = forms.ChoiceField(
        label="Tipo", choices=StockMovement.Type.choices, widget=forms.Select(attrs=_INPUT)
    )
    quantity = forms.DecimalField(
        label="Quantidade",
        max_digits=12,
        decimal_places=3,
        min_value=0.001,
        widget=forms.NumberInput(attrs={**_INPUT_DADOS, "step": "0.001", "min": "0.001"}),
        error_messages={"min_value": "A quantidade tem de ser maior que zero."},
    )
    occurred_at = forms.DateTimeField(
        label="Data e hora",
        widget=forms.DateTimeInput(attrs={**_INPUT_DADOS, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        input_formats=["%Y-%m-%dT%H:%M"],
    )
    reason = forms.CharField(
        label="Motivo",
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={**_INPUT, "placeholder": "Ex.: receção do fornecedor, quebra, contagem"}),
    )
    reference = forms.CharField(
        label="Referência",
        required=False,
        max_length=80,
        widget=forms.TextInput(attrs={**_INPUT, "placeholder": "Ex.: guia n.º 4412"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields["occurred_at"].initial = timezone.localtime().strftime("%Y-%m-%dT%H:%M")
