"""
Configuração do restaurante (Fases 5 e 6), só para o Admin (secção 7):
áreas de trabalho, tipos de pausa, tipos de ausência, feriados do
restaurante e períodos bloqueados.

Um CRUD genérico por secção. As tabelas para que apontam registos já
feitos (áreas, tipos) arquivam-se em vez de se apagarem; feriados e
períodos bloqueados apagam-se.
"""
from dataclasses import dataclass, field

from django import forms
from django.contrib import messages
from django.db.models import ProtectedError
from django.forms import modelform_factory
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from attendance.models import BreakType
from core.mixins import AdminRequiredMixin
from core.models import Restaurant, WorkArea
from vacations.holidays import national_holidays
from vacations.models import AbsenceType, BlockedPeriod, Holiday
from workers.models import Worker


@dataclass
class Secao:
    slug: str
    titulo: str
    singular: str
    model: type
    fields: list
    colunas: list  # (atributo, cabeçalho)
    ajuda: str = ""
    arquiva: bool = True
    widgets: dict = field(default_factory=dict)


_DATA = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")

SECOES = {
    s.slug: s
    for s in [
        Secao(
            "areas", "Áreas de trabalho", "área", WorkArea, ["name"], [("name", "Nome")],
            ajuda="Cozinha, sala, bar. Cada dispositivo fica numa área e as marcações herdam-na.",
        ),
        Secao(
            "pausas", "Tipos de pausa", "tipo de pausa", BreakType, ["name", "paid"],
            [("name", "Nome"), ("paid", "Paga")],
            ajuda="As pausas não pagas não contam para as horas trabalhadas.",
        ),
        Secao(
            "ausencias", "Tipos de ausência", "tipo de ausência", AbsenceType,
            ["name", "color", "deducts_balance", "requires_approval", "half_days"],
            [("name", "Nome"), ("deducts_balance", "Desconta férias"), ("requires_approval", "Aprovação"),
             ("half_days", "Meio dia")],
            ajuda="Um tipo sem aprovação fica aprovado logo que é pedido.",
        ),
        Secao(
            "feriados", "Feriados do restaurante", "feriado", Holiday, ["date", "name", "half_day"],
            [("date", "Data"), ("name", "Nome"), ("half_day", "Meio dia")],
            ajuda="Feriados municipais e dias de fecho. Os nacionais já estão incluídos e aparecem em baixo.",
            arquiva=False, widgets={"date": _DATA},
        ),
        Secao(
            "bloqueios", "Períodos bloqueados", "período bloqueado", BlockedPeriod,
            ["name", "start", "end", "absence_types", "exempt_workers"],
            [("name", "Motivo"), ("start", "Início"), ("end", "Fim")],
            ajuda="Datas em que a equipa não pode pedir ausências, como a época alta. "
                  "Sem tipos escolhidos, bloqueia todos. O gerente pode registar ausências na mesma.",
            arquiva=False,
            widgets={"start": _DATA, "end": _DATA,
                     "absence_types": forms.CheckboxSelectMultiple, "exempt_workers": forms.CheckboxSelectMultiple},
        ),
    ]
}


def _secao(slug):
    try:
        return SECOES[slug]
    except KeyError:
        raise Http404


def _restaurant(user):
    return user.restaurant or Restaurant.objects.first()


def _form_class(secao):
    return modelform_factory(secao.model, fields=secao.fields, widgets=secao.widgets)


def _preparar(form, restaurant):
    """Estilo do sistema de design e escolhas limitadas ao restaurante."""
    for nome, campo in form.fields.items():
        widget = campo.widget
        if isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
            continue
        widget.attrs["class"] = "campo-input" + (" font-dados" if isinstance(widget, forms.DateInput) else "")
    if "absence_types" in form.fields:
        form.fields["absence_types"].queryset = AbsenceType.objects.filter(restaurant=restaurant, archived_at__isnull=True)
    if "exempt_workers" in form.fields:
        form.fields["exempt_workers"].queryset = Worker.objects.filter(restaurant=restaurant, is_active=True)
    return form


class ConfigHomeView(AdminRequiredMixin, View):
    def get(self, request):
        restaurant = _restaurant(request.user)
        secoes = [
            (s, s.model.objects.filter(restaurant=restaurant).count()) for s in SECOES.values()
        ]
        return render(request, "manage/config/inicio.html", {"secoes": secoes})


class ConfigListView(AdminRequiredMixin, View):
    def get(self, request, secao):
        s = _secao(secao)
        restaurant = _restaurant(request.user)
        qs = s.model.objects.filter(restaurant=restaurant)
        if s.arquiva:
            qs = qs.order_by("archived_at", "name")
        linhas = [
            {"obj": obj, "valores": [getattr(obj, attr) for attr, _ in s.colunas]} for obj in qs
        ]
        contexto = {"secao": s, "linhas": linhas}
        if s.slug == "feriados":
            ano = timezone.localdate().year
            contexto["nacionais"] = sorted(national_holidays(ano).items())
            contexto["ano"] = ano
        return render(request, "manage/config/lista.html", contexto)


class ConfigFormView(AdminRequiredMixin, View):
    def _obj(self, request, s, pk):
        if pk is None:
            return None
        return get_object_or_404(s.model, pk=pk, restaurant=_restaurant(request.user))

    def get(self, request, secao, pk=None):
        s = _secao(secao)
        restaurant = _restaurant(request.user)
        form = _preparar(_form_class(s)(instance=self._obj(request, s, pk)), restaurant)
        return render(request, "manage/config/form.html", {"secao": s, "form": form, "novo": pk is None})

    def post(self, request, secao, pk=None):
        s = _secao(secao)
        restaurant = _restaurant(request.user)
        obj = self._obj(request, s, pk)
        form = _preparar(_form_class(s)(request.POST, instance=obj), restaurant)
        if form.is_valid():
            novo = form.save(commit=False)
            novo.restaurant = restaurant
            try:
                novo.validate_constraints()
            except forms.ValidationError as exc:
                form.add_error(None, " ".join(exc.messages))
            else:
                novo.save()
                form.save_m2m()
                messages.success(request, "Guardado")
                return redirect("config:lista", secao=s.slug)
        return render(request, "manage/config/form.html", {"secao": s, "form": form, "novo": pk is None})


class ConfigRemoveView(AdminRequiredMixin, View):
    """Arquivar (ou repor) nas secções arquiváveis; apagar nas outras."""

    def post(self, request, secao, pk):
        s = _secao(secao)
        obj = get_object_or_404(s.model, pk=pk, restaurant=_restaurant(request.user))
        if s.arquiva:
            obj.archived_at = None if obj.archived_at else timezone.now()
            obj.save(update_fields=["archived_at", "updated_at"])
            messages.success(request, "Reposto" if obj.archived_at is None else "Arquivado")
        else:
            try:
                obj.delete()
                messages.success(request, "Apagado")
            except ProtectedError:
                messages.error(request, "Não se pode apagar: há registos que dependem disto.")
        return redirect("config:lista", secao=s.slug)
