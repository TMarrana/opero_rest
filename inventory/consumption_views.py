"""
Consumos internos no backoffice (Fase 12). O mapa e a lista veem-nos o
Admin, o Gerente e o Responsável de stock; registar, alterar e anular os
consumos dos outros e os da casa é só do Gerente e do Admin (decidido a
2026-11-04). Os próprios consumos, cada trabalhador regista-os na app do
colaborador. As regras são do Admin.
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

from accounts.models import User
from attendance.month import month_start, next_month, previous_month
from core import exports
from core.mixins import AdminRequiredMixin, ManagerRequiredMixin, StockRequiredMixin
from core.utils import parse_decimal, restaurant_scope, workers_scope
from workers.models import Worker

from . import consumption as servico
from .models import ConsumptionSettings, InternalConsumption, Item

LINHAS_INICIAIS = 3
LINHAS_MAX = 20
CASA = "casa"
PODEM_REGISTAR = (User.Role.ADMIN, User.Role.MANAGER)


def linhas_formulario(dados):
    """As linhas para o formulário: LINHAS_MAX, das quais se veem as
    preenchidas e pelo menos LINHAS_INICIAIS; o + mostra as outras."""
    preenchidas = [n for n in range(LINHAS_MAX) if dados.get(f"item-{n}") or dados.get(f"qtd-{n}")]
    visiveis = max(LINHAS_INICIAIS, (preenchidas[-1] + 1) if preenchidas else 0)
    linhas = [{"n": n, "item": dados.get(f"item-{n}", ""), "qtd": dados.get(f"qtd-{n}", "")} for n in range(LINHAS_MAX)]
    return linhas, visiveis


def artigos_com_stock(artigos, consumo=None):
    """Os artigos ativos com o stock disponível (`disponivel`), para o aviso
    de stock negativo. Ao alterar um consumo, as quantidades dele voltam ao
    stock antes do novo registo e por isso contam como disponíveis."""
    devolve = {}
    if consumo is not None:
        for l in consumo.lines.all():
            devolve[l.item_id] = devolve.get(l.item_id, 0) + l.quantity
    artigos = list(artigos)
    for a in artigos:
        a.disponivel = a.current_stock + devolve.get(a.pk, 0)
    return artigos


def _numero(valor):
    return format(valor.normalize(), "f").replace(".", ",")


def dados_de(consumo):
    """O formulário preenchido com um consumo, para o alterar."""
    dados = {
        "pessoa": str(consumo.worker_id) if consumo.worker_id else CASA,
        "dia": consumo.consumed_on.isoformat(),
        "motivo": consumo.reason,
        "nota": consumo.note,
    }
    for n, l in enumerate(consumo.lines.all()):
        dados[f"item-{n}"] = str(l.item_id)
        dados[f"qtd-{n}"] = _numero(l.quantity)
    return dados


def avisar_resultado(request, consumo):
    """Mensagens depois de registar: limite de refeições e stock negativo."""
    if consumo.over_limit:
        _, limite = servico.meals_check(worker=consumo.worker, day=consumo.consumed_on, restaurant=consumo.restaurant)
        motivo = "não tinha turno nesse dia" if not limite else f"o limite é {limite} para os turnos desse dia"
        messages.warning(
            request,
            f"{consumo.who} passou o limite de refeições de {consumo.consumed_on:%d/%m}: {motivo}. "
            "Ficou registado e assinalado.",
        )
    if consumo.negativos:
        artigos = "; ".join(f"{item.name} em {_numero(stock)} {item.unit}" for item, stock in consumo.negativos)
        messages.warning(
            request,
            f"Stock negativo: {artigos}.",
        )


def dia_de(valor):
    try:
        return datetime.date.fromisoformat(valor)
    except ValueError:
        return None


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
                "pode_registar": request.role in PODEM_REGISTAR,
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


class ConsumptionCreateView(ManagerRequiredMixin, View):
    """Registar um consumo, ou alterar um (`pk`): o antigo fica anulado e
    o novo regista-se no seu lugar."""

    template_name = "manage/inventory/consumo_form.html"

    def _consumo(self, request, pk):
        if pk is None:
            return None
        return get_object_or_404(
            restaurant_scope(request, InternalConsumption.objects.filter(cancelled_at__isnull=True)), pk=pk
        )

    def _render(self, request, dados, consumo=None, erro=None, status=200):
        linhas, visiveis = linhas_formulario(dados)
        return render(
            request,
            self.template_name,
            {
                "dados": dados,
                "linhas": linhas,
                "visiveis": visiveis,
                "consumo": consumo,
                "erro": erro,
                "hoje": timezone.localdate(),
                "dia": dados.get("dia") or timezone.localdate().isoformat(),
                "motivos": InternalConsumption.Reason.choices,
                "trabalhadores": workers_scope(request, Worker.objects.filter(is_active=True)).order_by("full_name"),
                "artigos": artigos_com_stock(
                    restaurant_scope(request, Item.objects.filter(is_active=True)).order_by("name"), consumo
                ),
                "regras": ConsumptionSettings.for_restaurant(request.restaurant),
            },
            status=status,
        )

    def get(self, request, pk=None):
        consumo = self._consumo(request, pk)
        if consumo is not None:
            return self._render(request, dados_de(consumo), consumo)
        return self._render(request, {"motivo": InternalConsumption.Reason.REFEICAO, "pessoa": request.GET.get("pessoa", "")})

    def post(self, request, pk=None):
        antigo = self._consumo(request, pk)
        dados = request.POST
        try:
            artigos = {str(i.pk): i for i in restaurant_scope(request, Item.objects.filter(is_active=True))}
            campos = dict(
                worker=self._pessoa(request, dados.get("pessoa", "")),
                reason=dados.get("motivo", ""),
                day=dia_de(dados.get("dia", "")),
                lines=servico.parse_lines(dados, artigos, parse_decimal),
                user=request.user,
                note=dados.get("nota", "").strip()[:200],
            )
            if antigo is None:
                consumo = servico.register_consumption(restaurant=request.restaurant, **campos)
            else:
                consumo = servico.replace_consumption(consumption=antigo, **campos)
        except ValidationError as exc:
            return self._render(request, dados, antigo, erro=" ".join(exc.messages), status=400)
        if antigo is None:
            messages.success(request, f"Consumo {consumo.reference} registado")
        else:
            messages.success(request, f"Consumo {antigo.reference} alterado: ficou {consumo.reference}")
        avisar_resultado(request, consumo)
        return redirect(f"{_url_lista()}?mes={consumo.consumed_on:%Y-%m}")

    def _pessoa(self, request, valor):
        if valor == CASA:
            return None
        if not valor.isdigit():
            raise ValidationError("Escolha quem consumiu: um trabalhador, ou a casa.")
        return get_object_or_404(workers_scope(request, Worker.objects.all()), pk=int(valor))


def _url_lista():
    return reverse("inventory:consumos")


class ConsumptionCancelView(ManagerRequiredMixin, View):
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
