from django import forms

from .models import SalesSettings

_INPUT = {"class": "campo-input"}
MAX_UPLOAD_MB = 100


class ImportForm(forms.Form):
    ficheiro = forms.FileField(
        label="Ficheiro SAF-T",
        help_text="O ficheiro de faturação que o POS exporta, em XML ou dentro de um .zip.",
        widget=forms.ClearableFileInput(attrs={"class": "campo-input", "accept": ".xml,.zip"}),
    )

    def clean_ficheiro(self):
        f = self.cleaned_data["ficheiro"]
        if f.size > MAX_UPLOAD_MB * 1024 * 1024:
            raise forms.ValidationError(
                f"O ficheiro tem mais de {MAX_UPLOAD_MB} MB. Exporte um período mais curto, por exemplo um mês."
            )
        return f


class SalesSettingsForm(forms.ModelForm):
    class Meta:
        model = SalesSettings
        fields = ["day_cutoff_hour", "series", "hourly_cost", "stock_enabled", "stock_from"]
        widgets = {
            "day_cutoff_hour": forms.NumberInput(attrs={"class": "campo-input font-dados w-24", "min": 0, "max": 11}),
            "series": forms.TextInput(attrs={**_INPUT, "class": "campo-input font-dados"}),
            "hourly_cost": forms.NumberInput(attrs={"class": "campo-input font-dados w-32", "step": "0.01", "min": 0}),
            "stock_from": forms.DateInput(attrs={"class": "campo-input font-dados w-44", "type": "date"}, format="%Y-%m-%d"),
        }

    def clean_day_cutoff_hour(self):
        hora = self.cleaned_data["day_cutoff_hour"]
        if hora > 11:
            raise forms.ValidationError("A hora de corte é de madrugada: entre 0 e 11.")
        return hora

    def clean(self):
        dados = super().clean()
        if dados.get("stock_enabled") and not dados.get("stock_from"):
            self.add_error("stock_from", "Indique a partir de que dia as vendas tiram do stock.")
        return dados

    def clean_series(self):
        return ", ".join(s.strip() for s in self.cleaned_data["series"].split(",") if s.strip())
