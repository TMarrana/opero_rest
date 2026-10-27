"""
Consumos internos no backoffice (Fase 12). Registam o Admin, o Gerente e o
Responsável de stock (matriz da secção 7); as regras são do Admin.
"""
import datetime

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from attendance.month import month_start, next_month, previous_month
from core import exports
from core.mixins import AdminRequiredMixin, StockRequiredMixin
from core.utils import parse_decimal, restaurant_scope, workers_scope
from workers.models import Worker

from . import consumption as servico
from .models import ConsumptionSettings, InternalConsumption, Item

LINHAS = 6
CASA = "casa"


def _mes(request):
    try:
        return datetime.datetime.strptime(request.GET.get("mes", ""), "%Y-%m").date()
    except ValueError:
        return month_start(timezone.localdate())


class ConsumptionListView(StockRequiredMixin, View):
    """O mês: o mapa por pessoa e os consumos registados, com a exportação
    para o contabilista."""

    def get(self, request):
        mes = _mes(request)
        exportar = request.GET.get("exportar")
        formato = exports.formato_pedido(request)
        if exportar and not formato:
            # O mapa do mês para o contabilista (Fase 12), como sempre foi.
            resp = HttpResponse(servico.export_csv(request.restaurant, mes), content_type="text/csv; charset=utf-8")
            resp["Content-Disposition"] = f'attachment; filename="consumos-{mes:%Y-%m}.csv"'
            return resp
        consumos = (
            restaurant_scope(request, InternalConsumption.objects.select_related("worker", "created_by", "cancelled_by"))
            .filter(consumed_on__gte=mes, consumed_on__lt=next_month(mes))
            .prefetch_related("lines__item")
        )
        pessoa = request.GET.get("pessoa", "")
        if pessoa == CASA:
            consumos = consumos.filter(worker__isnull=True)
        elif pessoa.isdigit():
            consumos = consumos.filter(worker_id=int(pessoa))
        if formato:
            return exports.responder(
                formato,
                [_tabela_consumos(consumos), _tabela_mapa(servico.month_map(request.restaurant, mes))],
                f"consumos-{mes:%Y-%m}",
            )
        return render(
            request,
            "manage/inventory/consumos.html",
            {
                "mes": mes,
                "mes_anterior": previous_month(mes),
                "mes_seguinte": next_month(mes) if next_month(mes) <= timezone.localdate() else None,
                "mapa": servico.month_map(request.restaurant, mes),
                "consumos": consumos,
                "pessoa": pessoa,
                "trabalhadores": workers_scope(request, Worker.objects.all()).order_by("full_name"),
                "regras": ConsumptionSettings.for_restaurant(request.restaurant),
            },
        )


def _tabela_consumos(consumos):
    """Os consumos do mês com o filtro da pessoa, uma linha por artigo, com
    os anulados assinalados (Fase 15)."""
    return exports.Tabela(
        titulo="Consumos",
        colunas=["Referência", "Dia", "Quem", "Motivo", "Artigo", "Quantidade", "Unidade", "Custo unitário", "Valor",
                 "Acima do limite", "Anulado em", "Motivo da anulação", "Observação"],
        linhas=[
            [c.reference, c.consumed_on, c.who, c.get_reason_display(), l.item.name, l.quantity, l.item.unit, l.unit_cost,
             l.value, c.over_limit, c.cancelled_at, c.cancel_reason, c.note]
            for c in consumos.order_by("consumed_on", "pk")
            for l in c.lines.all()
        ],
        formatos=[exports.TEXTO, exports.DATA, exports.TEXTO, exports.TEXTO, exports.TEXTO, exports.NUMERO, exports.TEXTO,
                  exports.EUROS, exports.EUROS, exports.TEXTO, exports.DATAHORA],
    )


def _tabela_mapa(mapa):
    return exports.Tabela(
        titulo="Mapa do mês",
        colunas=["Quem", "Refeições", "Outros consumos", "Acima do limite", "Valor ao custo", "Linhas sem custo"],
        linhas=[[l["quem"], l["refeicoes"], l["outros"], l["acima"], l["valor"], l["sem_custo"]] for l in mapa],
        formatos=[exports.TEXTO, exports.NUMERO, exports.NUMERO, exports.NUMERO, exports.EUROS, exports.NUMERO],
    )


class ConsumptionCreateView(StockRequiredMixin, View):
    template_name = "manage/inventory/consumo_form.html"

    def _render(self, request, dados, erro=None, status=200):
        linhas = [
            {"n": n, "item": dados.get(f"item-{n}", ""), "qtd": dados.get(f"qtd-{n}", "")} for n in range(LINHAS)
        ]
        return render(
            request,
            self.template_name,
            {
                "dados": dados,
                "linhas": linhas,
                "erro": erro,
                "hoje": timezone.localdate(),
                "dia": dados.get("dia") or timezone.localdate().isoformat(),
                "motivos": InternalConsumption.Reason.choices,
                "trabalhadores": workers_scope(request, Worker.objects.filter(is_active=True)).order_by("full_name"),
                "artigos": restaurant_scope(request, Item.objects.filter(is_active=True)).order_by("name"),
                "regras": ConsumptionSettings.for_restaurant(request.restaurant),
            },
            status=status,
        )

    def get(self, request):
        return self._render(request, {"motivo": InternalConsumption.Reason.REFEICAO, "pessoa": request.GET.get("pessoa", "")})

    def post(self, request):
        dados = request.POST
        try:
            consumo = servico.register_consumption(
                restaurant=request.restaurant,
                worker=self._pessoa(request, dados.get("pessoa", "")),
                reason=dados.get("motivo", ""),
                day=self._dia(dados.get("dia", "")),
                lines=self._linhas(request, dados),
                user=request.user,
                note=dados.get("nota", "").strip()[:200],
            )
        except ValidationError as exc:
            return self._render(request, dados, erro=" ".join(exc.messages), status=400)
        messages.success(request, f"Consumo {consumo.reference} registado")
        if consumo.over_limit:
            _, limite = servico.meals_check(worker=consumo.worker, day=consumo.consumed_on, restaurant=consumo.restaurant)
            motivo = "não tinha turno nesse dia" if not limite else f"o limite é {limite} para os turnos desse dia"
            messages.warning(
                request,
                f"{consumo.who} passou o limite de refeições de {consumo.consumed_on:%d/%m}: {motivo}. "
                "Ficou registado e assinalado.",
            )
        return redirect(f"{_url_lista()}?mes={consumo.consumed_on:%Y-%m}")

    def _pessoa(self, request, valor):
        if valor == CASA:
            return None
        if not valor.isdigit():
            raise ValidationError("Escolha quem consumiu: um trabalhador, ou a casa.")
        return get_object_or_404(workers_scope(request, Worker.objects.all()), pk=int(valor))

    def _dia(self, valor):
        try:
            return datetime.date.fromisoformat(valor)
        except ValueError:
            return None

    def _linhas(self, request, dados):
        artigos = {str(i.pk): i for i in restaurant_scope(request, Item.objects.filter(is_active=True))}
        linhas = []
        for n in range(LINHAS):
            item = artigos.get(dados.get(f"item-{n}", ""))
            qtd = parse_decimal(dados.get(f"qtd-{n}"), "A quantidade")
            if item is None:
                if qtd:
                    raise ValidationError("Há uma quantidade numa linha sem artigo. Escolha o artigo.")
                continue
            if qtd is None:
                raise ValidationError(f"Indique a quantidade de {item}.")
            linhas.append((item, qtd))
        return linhas


def _url_lista():
    return reverse("inventory:consumos")


class ConsumptionCancelView(StockRequiredMixin, View):
    def post(self, request, pk):
        consumo = get_object_or_404(restaurant_scope(request, InternalConsumption.objects.all()), pk=pk)
        try:
            servico.cancel_consumption(consumption=consumo, user=request.user, reason=request.POST.get("motivo", ""))
            messages.success(request, f"Consumo {consumo.reference} anulado")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect(f"{_url_lista()}?mes={consumo.consumed_on:%Y-%m}")


class ConsumptionSettingsForm(forms.ModelForm):
    class Meta:
        model = ConsumptionSettings
        fields = ["meals_per_shift"]
        widgets = {"meals_per_shift": forms.NumberInput(attrs={"class": "campo-input font-dados w-24", "min": 0})}


class ConsumptionSettingsView(AdminRequiredMixin, View):
    template_name = "manage/inventory/consumo_regras.html"

    def get(self, request):
        regras = ConsumptionSettings.for_restaurant(request.restaurant)
        return render(request, self.template_name, {"form": ConsumptionSettingsForm(instance=regras)})

    def post(self, request):
        regras = ConsumptionSettings.for_restaurant(request.restaurant)
        form = ConsumptionSettingsForm(request.POST, instance=regras)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form}, status=400)
        form.save()
        messages.success(request, "Regras dos consumos guardadas")
        return redirect("inventory:consumos")
