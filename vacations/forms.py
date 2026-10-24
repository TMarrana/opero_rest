from django import forms

from workers.models import Worker

from .models import AbsenceType, Allowance

_INPUT = {"class": "campo-input"}
_DATA = {"class": "campo-input font-dados", "type": "date"}


class VacationRequestForm(forms.Form):
    """Pedido de ausência. O campo do trabalhador só existe no backoffice;
    na vista staff o pedido é sempre do próprio."""

    worker = forms.ModelChoiceField(label="Trabalhador", queryset=Worker.objects.none(), widget=forms.Select(attrs=_INPUT))
    absence_type = forms.ModelChoiceField(
        label="Tipo",
        queryset=AbsenceType.objects.none(),
        widget=forms.Select(attrs=_INPUT),
        empty_label=None,
        # Sem tipo, o pedido é de férias: o pedido de três campos da Fase 3
        # continua a funcionar.
        required=False,
    )
    start_date = forms.DateField(label="Início", widget=forms.DateInput(attrs=_DATA, format="%Y-%m-%d"))
    end_date = forms.DateField(label="Fim", widget=forms.DateInput(attrs=_DATA, format="%Y-%m-%d"))
    half_day = forms.BooleanField(label="Só meio dia", required=False)
    request_note = forms.CharField(
        label="Observação",
        required=False,
        max_length=300,
        widget=forms.TextInput(attrs={**_INPUT, "placeholder": "Ex.: casamento, viagem em família"}),
    )

    def __init__(self, *args, restaurant=None, with_worker=True, **kwargs):
        super().__init__(*args, **kwargs)
        workers = Worker.objects.filter(is_active=True)
        tipos = AbsenceType.objects.filter(archived_at__isnull=True)
        if restaurant is not None:
            workers = workers.filter(restaurant=restaurant)
            tipos = tipos.filter(restaurant=restaurant)
        if with_worker:
            self.fields["worker"].queryset = workers
        else:
            del self.fields["worker"]
        self.fields["absence_type"].queryset = tipos
        # Férias primeiro: é o pedido mais comum.
        self._ferias = tipos.filter(deducts_balance=True).first()
        if self._ferias is not None and not self.is_bound:
            self.initial.setdefault("absence_type", self._ferias.pk)
        if not tipos.filter(half_days=True).exists():
            del self.fields["half_day"]

    def clean(self):
        data = super().clean()
        inicio, fim = data.get("start_date"), data.get("end_date")
        if inicio and fim and fim < inicio:
            self.add_error("end_date", "O fim tem de ser igual ou depois do início.")
        if not data.get("absence_type"):
            if self._ferias is None:
                self.add_error("absence_type", "Escolha o tipo de ausência.")
            data["absence_type"] = self._ferias
        return data


class DecisionForm(forms.Form):
    decision_note = forms.CharField(
        label="Observação",
        required=False,
        max_length=300,
        widget=forms.TextInput(attrs={**_INPUT, "placeholder": "Opcional; fica no histórico do pedido"}),
    )


class AllowanceForm(forms.ModelForm):
    class Meta:
        model = Allowance
        fields = ["days", "carried_over", "carry_over_expires_on"]
        widgets = {
            "days": forms.NumberInput(attrs={"class": "campo-input font-dados w-20", "step": "0.5", "min": "0"}),
            "carried_over": forms.NumberInput(attrs={"class": "campo-input font-dados w-20", "step": "0.5", "min": "0"}),
            "carry_over_expires_on": forms.DateInput(attrs=_DATA, format="%Y-%m-%d"),
        }
