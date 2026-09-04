from django import forms

from workers.models import Worker

from .models import VacationRequest

_INPUT = {"class": "campo-input"}
_DATA = {"class": "campo-input font-dados", "type": "date"}


class VacationRequestForm(forms.ModelForm):
    class Meta:
        model = VacationRequest
        fields = ["worker", "start_date", "end_date", "request_note"]
        widgets = {
            "worker": forms.Select(attrs=_INPUT),
            "start_date": forms.DateInput(attrs=_DATA, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs=_DATA, format="%Y-%m-%d"),
            "request_note": forms.TextInput(attrs={**_INPUT, "placeholder": "Ex.: casamento, viagem em família"}),
        }

    def __init__(self, *args, restaurant=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Worker.objects.filter(is_active=True)
        if restaurant is not None:
            qs = qs.filter(restaurant=restaurant)
        self.fields["worker"].queryset = qs

    def clean(self):
        data = super().clean()
        inicio, fim = data.get("start_date"), data.get("end_date")
        if inicio and fim and fim < inicio:
            self.add_error("end_date", "O fim tem de ser igual ou depois do início.")
        return data


class DecisionForm(forms.Form):
    decision_note = forms.CharField(
        label="Observação",
        required=False,
        max_length=300,
        widget=forms.TextInput(attrs={**_INPUT, "placeholder": "Opcional; fica no histórico do pedido"}),
    )
