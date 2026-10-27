import datetime

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View

from core.mixins import ManagerRequiredMixin
from core.models import WorkArea
from core.utils import workers_scope
from vacations.models import VacationRequest
from workers.models import Worker

from . import services
from .models import RestDay, Shift, ShiftTemplate, WeekPublication

_HORA = {"class": "campo-input font-dados", "type": "time"}


def _semana(request):
    dia = parse_date(request.GET.get("semana") or request.POST.get("semana") or "") or timezone.localdate()
    return services.week_start(dia)


def _url_semana(semana, area=""):
    url = f"{reverse('shifts:planeador')}?semana={semana.isoformat()}"
    return f"{url}&area={area}" if area else url


def _templates(restaurant):
    return ShiftTemplate.objects.filter(restaurant=restaurant, archived_at__isnull=True)


class ShiftForm(forms.Form):
    """Turno numa célula: um turno guardado, ou horas à mão."""

    template = forms.ModelChoiceField(
        label="Turno guardado", queryset=ShiftTemplate.objects.none(), required=False,
        widget=forms.Select(attrs={"class": "campo-input"}), empty_label="Horas à mão",
    )
    start = forms.TimeField(label="Início", required=False, widget=forms.TimeInput(attrs=_HORA, format="%H:%M"))
    end = forms.TimeField(label="Fim", required=False, widget=forms.TimeInput(attrs=_HORA, format="%H:%M"))
    work_area = forms.ModelChoiceField(
        label="Área", queryset=WorkArea.objects.none(), required=False,
        widget=forms.Select(attrs={"class": "campo-input"}), empty_label="Sem área",
    )

    def __init__(self, *args, restaurant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["template"].queryset = _templates(restaurant)
        self.fields["work_area"].queryset = WorkArea.objects.filter(restaurant=restaurant, archived_at__isnull=True)


class BulkForm(forms.Form):
    template = forms.ModelChoiceField(
        label="Turno guardado", queryset=ShiftTemplate.objects.none(), widget=forms.Select(attrs={"class": "campo-input"})
    )
    workers = forms.ModelMultipleChoiceField(
        label="Trabalhadores", queryset=Worker.objects.none(), widget=forms.CheckboxSelectMultiple
    )
    days = forms.MultipleChoiceField(label="Dias", choices=[], widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, restaurant=None, semana=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["template"].queryset = _templates(restaurant)
        self.fields["workers"].queryset = Worker.objects.filter(is_active=True).in_restaurant(restaurant)
        self.fields["days"].choices = [
            (d.isoformat(), d.strftime("%a %d/%m")) for d in services.week_days(semana)
        ]


class PlannerView(ManagerRequiredMixin, View):
    """Grelha semanal por trabalhador, filtrável por área. Rascunhos com
    contorno tracejado, publicados a cheio, reservas e remoções à parte;
    ausências pendentes riscadas; conflitos a chama."""

    def get(self, request):
        restaurant = request.restaurant
        semana = _semana(request)
        dias = services.week_days(semana)
        area = request.GET.get("area", "")
        workers = workers_scope(request, Worker.objects.filter(is_active=True))
        turnos = Shift.objects.filter(restaurant=restaurant, work_date__range=(dias[0], dias[-1])).select_related(
            "template", "work_area"
        )
        # Os turnos de quem também trabalha noutra casa, só para consulta
        # (Fase 9). Os rascunhos de lá não aparecem.
        fora = {}
        for s in (
            Shift.objects.filter(
                worker__in=workers, work_date__range=(dias[0], dias[-1]), state=Shift.State.PUBLICADO
            )
            .exclude(restaurant=restaurant)
            .select_related("restaurant")
        ):
            fora.setdefault((s.worker_id, s.work_date), []).append(s)
        if area:
            turnos_area = turnos.filter(work_area_id=area)
            workers = workers.filter(pk__in=turnos_area.values("worker"))
        folgas = {
            (f.worker_id, f.date): f
            for f in RestDay.objects.filter(worker__in=workers, date__range=(dias[0], dias[-1]))
        }
        ausencias = VacationRequest.objects.filter(
            worker__in=workers,
            status__in=[VacationRequest.Status.APROVADO, VacationRequest.Status.PENDENTE],
            start_date__lte=dias[-1],
            end_date__gte=dias[0],
        ).select_related("absence_type")
        conflitos = services.conflicts(restaurant, semana)
        por_celula = {}
        for s in turnos:
            s.conflitos = conflitos.get(s.pk, [])
            por_celula.setdefault((s.worker_id, s.work_date), []).append(s)
        linhas = []
        for w in workers:
            celulas = []
            for d in dias:
                celulas.append(
                    {
                        "dia": d,
                        "turnos": por_celula.get((w.pk, d), []),
                        "fora": fora.get((w.pk, d), []),
                        "folga": folgas.get((w.pk, d)),
                        "ausencias": [a for a in ausencias if a.worker_id == w.pk and a.start_date <= d <= a.end_date],
                    }
                )
            total = sum(
                (s.duration for c in celulas for s in c["turnos"] if s.state != Shift.State.RESERVA and not s.pending_removal),
                datetime.timedelta(),
            )
            linhas.append(
                {"worker": w, "celulas": celulas, "total": total, "visita": w.restaurant_id != restaurant.pk}
            )
        mudancas = services.changes(restaurant, semana)
        return render(
            request,
            "manage/shifts/planeador.html",
            {
                "semana": semana,
                "dias": dias,
                "hoje": timezone.localdate(),
                "semana_anterior": semana - datetime.timedelta(days=7),
                "semana_seguinte": semana + datetime.timedelta(days=7),
                "linhas": linhas,
                "areas": WorkArea.objects.filter(restaurant=restaurant, archived_at__isnull=True),
                "area": area,
                "total_conflitos": len(conflitos),
                "por_publicar": sum(len(mudancas[k]) for k in ("novos", "alterados", "removidos", "folgas")),
                "tem_templates": _templates(restaurant).exists(),
                "ultima_publicacao": WeekPublication.objects.filter(restaurant=restaurant, week=semana).first(),
            },
        )


class CellView(ManagerRequiredMixin, View):
    """Painel de uma célula (trabalhador × dia): acrescentar turno, marcar
    ou tirar a folga, apagar ou despublicar um turno."""

    def _contexto(self, request, worker, dia, form=None):
        restaurant = request.restaurant
        return {
            "worker": worker,
            "dia": dia,
            "turnos": Shift.objects.filter(worker=worker, work_date=dia, restaurant=restaurant).select_related(
                "template"
            ),
            "fora": Shift.objects.filter(worker=worker, work_date=dia, state=Shift.State.PUBLICADO)
            .exclude(restaurant=restaurant)
            .select_related("restaurant"),
            "folga": RestDay.objects.filter(worker=worker, date=dia).select_related("restaurant").first(),
            "form": form or ShiftForm(restaurant=restaurant),
            "semana": services.week_start(dia),
        }

    def _worker(self, request, pk):
        return get_object_or_404(workers_scope(request, Worker.objects.all()), pk=pk)

    def get(self, request, worker, dia):
        dia = parse_date(dia)
        return render(request, "partials/shifts/celula.html", self._contexto(request, self._worker(request, worker), dia))

    def post(self, request, worker, dia):
        restaurant = request.restaurant
        worker = self._worker(request, worker)
        dia = parse_date(dia)
        acao = request.POST.get("acao")
        try:
            if acao == "turno":
                form = ShiftForm(request.POST, restaurant=restaurant)
                if not form.is_valid():
                    raise ValidationError("Verifique os campos do turno.")
                services.create_shift(
                    restaurant=restaurant, worker=worker, day=dia,
                    template=form.cleaned_data["template"], start=form.cleaned_data["start"],
                    end=form.cleaned_data["end"], work_area=form.cleaned_data["work_area"],
                )
                messages.success(request, "Turno acrescentado")
            elif acao == "folga":
                services.set_rest_day(restaurant=restaurant, worker=worker, day=dia)
                messages.success(request, "Folga marcada")
            elif acao == "tirar_folga":
                folga = get_object_or_404(RestDay, worker=worker, date=dia, restaurant=restaurant)
                services.remove_rest_day(rest_day=folga)
                messages.success(request, "Folga retirada")
            elif acao in ("apagar", "despublicar"):
                turno = get_object_or_404(Shift, pk=request.POST.get("turno"), worker=worker, restaurant=restaurant)
                if acao == "apagar":
                    services.remove_shift(shift=turno)
                    messages.success(request, "Turno apagado")
                else:
                    services.unpublish_shift(shift=turno)
                    messages.success(request, "Turno de volta a rascunho")
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        return redirect(_url_semana(services.week_start(dia)))


class BulkView(ManagerRequiredMixin, View):
    """Criar turnos em lote: um turno guardado para vários trabalhadores e
    vários dias da semana (R-034)."""

    def get(self, request):
        restaurant = request.restaurant
        semana = _semana(request)
        form = BulkForm(restaurant=restaurant, semana=semana)
        return render(request, "manage/shifts/lote.html", {"form": form, "semana": semana})

    def post(self, request):
        restaurant = request.restaurant
        semana = _semana(request)
        form = BulkForm(request.POST, restaurant=restaurant, semana=semana)
        if not form.is_valid():
            return render(request, "manage/shifts/lote.html", {"form": form, "semana": semana})
        criados = services.bulk_create(
            restaurant=restaurant,
            template=form.cleaned_data["template"],
            workers=form.cleaned_data["workers"],
            days=[parse_date(d) for d in form.cleaned_data["days"]],
        )
        messages.success(request, f"{criados} turno(s) criado(s) em rascunho")
        return redirect(_url_semana(semana))


class CopyWeekView(ManagerRequiredMixin, View):
    """Copiar a semana anterior para esta, em rascunho (R-038)."""

    def post(self, request):
        semana = _semana(request)
        turnos, folgas = services.copy_week(
            restaurant=request.restaurant, source=semana - datetime.timedelta(days=7), target=semana
        )
        if turnos or folgas:
            messages.success(request, f"Copiados {turnos} turno(s) e {folgas} folga(s), em rascunho")
        else:
            messages.error(request, "A semana anterior não tem nada para copiar, ou já estava tudo copiado.")
        return redirect(_url_semana(semana))


class PublishView(ManagerRequiredMixin, View):
    """Antes de publicar, o gerente vê o que mudou e quem é afetado; com
    conflitos, a publicação é recusada (R-032)."""

    def get(self, request):
        restaurant = request.restaurant
        semana = _semana(request)
        conflitos = services.conflicts(restaurant, semana)
        com_conflito = Shift.objects.filter(pk__in=conflitos).select_related("worker", "template")
        for s in com_conflito:
            s.conflitos = conflitos[s.pk]
        return render(
            request,
            "manage/shifts/publicar.html",
            {"semana": semana, "mudancas": services.changes(restaurant, semana), "com_conflito": com_conflito},
        )

    def post(self, request):
        semana = _semana(request)
        try:
            services.publish_week(restaurant=request.restaurant, week=semana, user=request.user)
            messages.success(request, "Semana publicada")
            return redirect(_url_semana(semana))
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect(f"{reverse('shifts:publicar')}?semana={semana.isoformat()}")
