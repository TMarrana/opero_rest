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


NOVO_ARTIGO = "novo"


class TransferForm(forms.Form):
    """Transferência para outra casa do grupo (Fase 9). O artigo de destino
    é um artigo da outra casa com a mesma unidade, ou um artigo novo lá,
    com o mesmo nome, a mesma unidade e a mesma categoria."""

    destination_item = forms.ChoiceField(label="Artigo na casa de destino", widget=forms.Select(attrs=_INPUT))
    quantity = forms.DecimalField(
        label="Quantidade",
        max_digits=12,
        decimal_places=3,
        min_value=0.001,
        widget=forms.NumberInput(attrs={**_INPUT_DADOS, "step": "0.001", "min": "0.001"}),
        error_messages={"min_value": "A quantidade tem de ser maior que zero."},
    )
    note = forms.CharField(
        label="Observação",
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={**_INPUT, "placeholder": "Ex.: falta para o jantar"}),
    )

    def __init__(self, *args, item, destino, **kwargs):
        super().__init__(*args, **kwargs)
        self.item, self.destino = item, destino
        self.candidatos = {
            str(i.pk): i for i in Item.objects.filter(restaurant=destino, unit=item.unit, is_active=True)
        }
        escolhas = [(pk, i.name) for pk, i in self.candidatos.items()]
        mesmo_nome = next((pk for pk, i in self.candidatos.items() if i.name.lower() == item.name.lower()), None)
        if mesmo_nome is None:
            escolhas.insert(0, (NOVO_ARTIGO, f"Criar «{item.name}» em {destino}"))
        self.fields["destination_item"].choices = escolhas
        self.fields["destination_item"].initial = mesmo_nome or NOVO_ARTIGO
        self.fields["quantity"].label = f"Quantidade ({item.get_unit_display()})"

    def destination(self):
        """O artigo de destino escolhido; cria-o se for um artigo novo."""
        escolha = self.cleaned_data["destination_item"]
        if escolha != NOVO_ARTIGO:
            return self.candidatos[escolha]
        categoria, _ = Category.objects.get_or_create(restaurant=self.destino, name=self.item.category.name)
        artigo, _ = Item.objects.get_or_create(
            restaurant=self.destino,
            name=self.item.name,
            defaults={"category": categoria, "unit": self.item.unit, "reference_cost": self.item.reference_cost},
        )
        return artigo
