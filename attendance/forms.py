from django import forms

_DADOS = {"class": "campo-input font-dados", "type": "datetime-local"}
_FMT = ["%Y-%m-%dT%H:%M"]


class EntryCorrectionForm(forms.Form):
    check_in = forms.DateTimeField(
        label="Entrada", widget=forms.DateTimeInput(attrs=_DADOS, format="%Y-%m-%dT%H:%M"), input_formats=_FMT
    )
    check_out = forms.DateTimeField(
        label="Saída",
        required=False,
        widget=forms.DateTimeInput(attrs=_DADOS, format="%Y-%m-%dT%H:%M"),
        input_formats=_FMT,
        help_text="Deixe vazio se o turno ainda está aberto.",
    )
    reason = forms.CharField(
        label="Motivo da correção",
        max_length=200,
        widget=forms.TextInput(attrs={"class": "campo-input", "placeholder": "Ex.: esqueceu-se de marcar a saída"}),
        error_messages={"required": "O motivo é obrigatório: fica no registo, junto com o seu nome."},
    )


class CorrectionRequestForm(forms.Form):
    """Pedido de correção do colaborador: entrada e saída propostas e o
    motivo, que vai para o gerente."""

    check_in = forms.DateTimeField(
        label="Entrada", widget=forms.DateTimeInput(attrs=_DADOS, format="%Y-%m-%dT%H:%M"), input_formats=_FMT
    )
    check_out = forms.DateTimeField(
        label="Saída", widget=forms.DateTimeInput(attrs=_DADOS, format="%Y-%m-%dT%H:%M"), input_formats=_FMT
    )
    note = forms.CharField(
        label="Motivo",
        max_length=200,
        widget=forms.TextInput(attrs={"class": "campo-input", "placeholder": "Ex.: esqueci-me de marcar a saída"}),
        error_messages={"required": "Diga porquê: o motivo vai para o gerente."},
    )


class CorrectionDecisionForm(forms.Form):
    decision_note = forms.CharField(
        label="Observação",
        required=False,
        max_length=300,
        widget=forms.TextInput(attrs={"class": "campo-input", "placeholder": "Opcional"}),
    )
