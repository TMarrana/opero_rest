"""
Vendas (Fase 10): importar o SAF-T e ver o que se vendeu, quando e por
quanto. Só o Admin e o Gerente (matriz da secção 7).
"""
import csv
import datetime
import io

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View

from attendance.month import month_range, next_month, previous_month
from core.mixins import AdminRequiredMixin, ManagerRequiredMixin

from . import reports
from .forms import ImportForm, SalesSettingsForm
from .models import SalesImport, SalesSettings
from .services import import_saft

MAX_DIAS = 366


def _data(valor):
    try:
        return datetime.date.fromisoformat(valor)
    except (TypeError, ValueError):
        return None


def _periodo(request):
    """(início, fim, mês ou None). Um intervalo `de`/`ate` válido manda;
    senão o mês pedido; senão o mês do último dia importado."""
    de, ate = _data(request.GET.get("de")), _data(request.GET.get("ate"))
    if de and ate and de <= ate and (ate - de).days < MAX_DIAS:
        return de, ate, None
    try:
        mes = datetime.datetime.strptime(request.GET.get("mes", ""), "%Y-%m").date()
    except ValueError:
        mes = (reports.ultimo_dia(request.restaurant) or timezone.localdate()).replace(day=1)
    inicio, fim = month_range(mes)
    return inicio, fim, mes


def _anterior(inicio, fim, mes, ultimo):
    """O período de comparação: o mês anterior, ou o mesmo número de dias
    logo antes. Um período ainda não todo importado (o mês corrente)
    compara-se só com os mesmos dias, para não dar uma queda que não houve."""
    if ultimo is not None and inicio <= ultimo < fim:
        fim = ultimo
    if mes is not None:
        ant_inicio, ant_fim = month_range(previous_month(mes))
        return ant_inicio, min(ant_fim, ant_inicio + (fim - inicio))
    dias = (fim - inicio).days + 1
    return inicio - datetime.timedelta(days=dias), inicio - datetime.timedelta(days=1)


def _num(valor):
    """Decimal com vírgula, como o Excel em português espera."""
    return "" if valor is None else str(valor).replace(".", ",")


def _horas(delta):
    return "" if delta is None else _num(round(delta.total_seconds() / 3600, 2))


def _csv(nome, cabecalho, linhas):
    saida = io.StringIO()
    escrita = csv.writer(saida, delimiter=";")
    escrita.writerow(cabecalho)
    escrita.writerows(linhas)
    resp = HttpResponse("﻿" + saida.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{nome}"'
    return resp


class SalesView(ManagerRequiredMixin, View):
    def get(self, request):
        casa = request.restaurant
        inicio, fim, mes = _periodo(request)
        exportar = request.GET.get("exportar")
        if exportar == "dias":
            linhas, totais = reports.por_dia(casa, inicio, fim)
            return _csv(
                f"vendas-por-dia-{inicio:%Y%m%d}-{fim:%Y%m%d}.csv",
                ["Dia", "Vendas sem IVA", "Documentos", "Ticket médio", "Horas trabalhadas", "Horas previstas", "Vendas por hora"],
                [
                    [l["dia"].isoformat(), _num(l["total"]), l["vendas"], _num(l["ticket"]), _horas(l["horas"]),
                     "sim" if l["previstas"] else "", _num(l["por_hora"])]
                    for l in linhas
                ]
                + [["Total", _num(totais["total"]), totais["vendas"], _num(totais["ticket"]), _horas(totais["horas"]), "",
                    _num(totais["por_hora"])]],
            )
        if exportar == "produtos":
            return _csv(
                f"vendas-por-produto-{inicio:%Y%m%d}-{fim:%Y%m%d}.csv",
                ["Código", "Produto", "Família", "Quantidade", "Vendas sem IVA"],
                [
                    [p["product__code"], p["product__description"], p["product__group"], _num(p["quantidade"]), _num(p["total"])]
                    for p in reports.por_produto(casa, inicio, fim)
                ],
            )

        ultimo = reports.ultimo_dia(casa)
        ant_inicio, ant_fim = _anterior(inicio, fim, mes, ultimo)
        atual, anterior = reports.resumo(casa, inicio, fim), reports.resumo(casa, ant_inicio, ant_fim)
        linhas, totais = reports.por_dia(casa, inicio, fim)
        hoje = timezone.localdate()
        contexto = {
            "inicio": inicio,
            "fim": fim,
            "mes": mes,
            "mes_anterior": previous_month(mes) if mes else None,
            "mes_seguinte": next_month(mes) if mes and next_month(mes) <= hoje else None,
            "anterior_inicio": ant_inicio,
            "anterior_fim": ant_fim,
            "atual": atual,
            "anterior": anterior,
            "var_total": reports.variacao(atual.total, anterior.total),
            "var_vendas": reports.variacao(atual.vendas, anterior.vendas),
            "var_ticket": reports.variacao(atual.ticket, anterior.ticket),
            "dias": linhas,
            "totais": totais,
            "mapa": reports.mapa_semana(casa, inicio, fim),
            "produtos": reports.por_produto(casa, inicio, fim)[:20],
            "familias": reports.por_familia(casa, inicio, fim),
            "regras": SalesSettings.for_restaurant(casa),
            "ultimo_dia": ultimo,
            "tem_importacoes": SalesImport.objects.filter(restaurant=casa).exists(),
            "query": f"de={inicio:%Y-%m-%d}&ate={fim:%Y-%m-%d}",
        }
        return render(request, "manage/sales/vendas.html", contexto)


class ImportView(ManagerRequiredMixin, View):
    template_name = "manage/sales/importar.html"

    def _render(self, request, form, erro=None, status=200):
        casa = request.restaurant
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "erro": erro,
                "importacoes": SalesImport.objects.filter(restaurant=casa).select_related("imported_by")[:20],
                "regras": SalesSettings.for_restaurant(casa),
            },
            status=status,
        )

    def get(self, request):
        return self._render(request, ImportForm())

    def post(self, request):
        form = ImportForm(request.POST, request.FILES)
        if not form.is_valid():
            return self._render(request, form, status=400)
        try:
            importacao = import_saft(restaurant=request.restaurant, upload=form.cleaned_data["ficheiro"], user=request.user)
        except ValidationError as exc:
            return self._render(request, ImportForm(), erro=" ".join(exc.messages), status=400)
        messages.success(request, f"Ficheiro importado: {importacao.documents_new} documento(s) novo(s)")
        return redirect("sales:importar")


class SettingsView(AdminRequiredMixin, View):
    """Regras de vendas da casa: hora de corte, séries e custo por hora."""

    template_name = "manage/sales/regras.html"

    def get(self, request):
        regras = SalesSettings.for_restaurant(request.restaurant)
        return render(request, self.template_name, {"form": SalesSettingsForm(instance=regras)})

    def post(self, request):
        regras = SalesSettings.for_restaurant(request.restaurant)
        form = SalesSettingsForm(request.POST, instance=regras)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form}, status=400)
        form.save()
        messages.success(request, "Regras de vendas guardadas")
        return redirect("sales:importar")
