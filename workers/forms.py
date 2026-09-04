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
        help_texts = {"user": "Liga este trabalhador a um utilizador para ele marcar o próprio ponto."}

    def __init__(self, *args, restaurant=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = User.objects.filter(is_active=True)
        if restaurant is not None:
            qs = qs.filter(restaurant=restaurant)
        livres = qs.filter(worker__isnull=True)
        if self.instance.pk and self.instance.user_id:
            livres = livres | qs.filter(pk=self.instance.user_id)
        self.fields["user"].queryset = livres.distinct()
