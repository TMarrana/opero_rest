"""
Vendas (Fase 10): importar o SAF-T e ver o que se vendeu, quando e por
quanto. Só o Admin e o Gerente (matriz da secção 7).
"""
import csv
import datetime
import io

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View

from attendance.month import month_range, next_month, previous_month
from core import exports
from core.mixins import AdminRequiredMixin, ManagerRequiredMixin

from . import reports, stock
from .forms import ImportForm, SalesSettingsForm
from .models import SaleStockMovement, SalesImport, SalesSettings
from .services import import_saft

MAX_DIAS = 366
# Vendas → Stock mostra os problemas dos últimos dias aplicados.
DIAS_STOCK = 30


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


def _tabela_dias(casa, inicio, fim):
    linhas, totais = reports.por_dia(casa, inicio, fim)
    return exports.Tabela(
        titulo="Vendas por dia",
        colunas=["Dia", "Vendas sem IVA", "Documentos", "Ticket médio", "Horas trabalhadas", "Horas previstas",
                 "Vendas por hora", "Custo de pessoal (%)"],
        linhas=[
            [l["dia"], l["total"], l["vendas"], l["ticket"], l["horas"], l["previstas"], l["por_hora"], l["custo_pessoal"]]
            for l in linhas
        ]
        + [["Total", totais["total"], totais["vendas"], totais["ticket"], totais["horas"], "", totais["por_hora"],
            totais["custo_pessoal"]]],
        formatos=[exports.DATA, exports.EUROS, exports.NUMERO, exports.EUROS, exports.HORAS, exports.TEXTO, exports.EUROS,
                  exports.PERCENTAGEM],
    )


def _tabela_produtos(casa, inicio, fim):
    return exports.Tabela(
        titulo="Vendas por produto",
        colunas=["Código", "Produto", "Família", "Quantidade", "Vendas sem IVA"],
        linhas=[
            [p["product__code"], p["product__description"], p["product__group"], p["quantidade"], p["total"]]
            for p in reports.por_produto(casa, inicio, fim)
        ],
        formatos=[exports.TEXTO] * 3 + [exports.NUMERO, exports.EUROS],
    )


class SalesView(ManagerRequiredMixin, View):
    def get(self, request):
        casa = request.restaurant
        inicio, fim, mes = _periodo(request)
        exportar = request.GET.get("exportar")
        if exportar in ("dias", "produtos") and request.GET.get("formato") == "xlsx":
            nome = f"vendas-por-{'dia' if exportar == 'dias' else 'produto'}-{inicio:%Y%m%d}-{fim:%Y%m%d}"
            tabela = _tabela_dias(casa, inicio, fim) if exportar == "dias" else _tabela_produtos(casa, inicio, fim)
            return exports.xlsx_response([tabela], nome)
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
        _mensagem_stock(request, importacao.stock_results)
        return redirect("sales:importar")


class SettingsView(AdminRequiredMixin, View):
    """Regras de vendas da casa: hora de corte, séries e custo por hora."""

    template_name = "manage/sales/regras.html"

    def get(self, request):
        regras = SalesSettings.for_restaurant(request.restaurant)
        return render(request, self.template_name, {"form": SalesSettingsForm(instance=regras)})

    def post(self, request):
        regras = SalesSettings.for_restaurant(request.restaurant)
        antes = (regras.stock_enabled, regras.stock_from)
        form = SalesSettingsForm(request.POST, instance=regras)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form}, status=400)
        with transaction.atomic():
            regras = form.save()
            # Ao ligar, ou ao mudar o dia de início, os dias já importados
            # desde esse dia tiram do stock o que ainda não tiraram.
            resultados = []
            if regras.stock_enabled and antes != (regras.stock_enabled, regras.stock_from):
                resultados = stock.apply_since(restaurant=request.restaurant, user=request.user)
        messages.success(request, "Regras de vendas guardadas")
        _mensagem_stock(request, resultados)
        return redirect("sales:importar")


def _mensagem_stock(request, resultados):
    """O que as vendas fizeram ao stock, depois de uma importação ou de ligar
    o stock pelas vendas (Fase 14)."""
    if not resultados:
        return
    resumo = stock.summary(resultados)
    texto = f"Stock atualizado pelas vendas de {resumo['dias']} dia(s): {resumo['movimentos']} movimento(s)"
    if resumo["problemas"]:
        texto += f". {len(resumo['problemas'])} problema(s) deixaram vendas por abater: veja Vendas → Stock"
        messages.warning(request, texto)
    else:
        messages.success(request, texto)


class StockView(ManagerRequiredMixin, View):
    """Vendas → Stock (Fase 14): se a casa tem o stock pelas vendas ligado,
    os últimos dias aplicados e o que ficou por abater, com a razão."""

    template_name = "manage/sales/stock.html"

    def get(self, request):
        casa = request.restaurant
        regras = SalesSettings.for_restaurant(casa)
        hoje = timezone.localdate()
        desde = hoje - datetime.timedelta(days=DIAS_STOCK)
        contexto = {"regras": regras, "desde": desde}
        if regras.stock_enabled and regras.stock_from:
            inicio = max(desde, regras.stock_from)
            contexto["resumo"] = stock.problems_since(casa, inicio, hoje)
            contexto["inicio"] = inicio
            contexto["dias"] = (
                SaleStockMovement.objects.filter(restaurant=casa, service_date__gte=inicio)
                .values("service_date")
                .annotate(movimentos=Count("pk"), artigos=Count("item", distinct=True))
                .order_by("-service_date")
            )
        return render(request, self.template_name, contexto)

    def post(self, request):
        """Depois de corrigir uma ficha ou um artigo: volta a aplicar os dias
        desde o início. Só entra a diferença, por isso repetir não muda nada."""
        resultados = stock.apply_since(restaurant=request.restaurant, user=request.user)
        if not resultados:
            messages.error(request, "O stock pelas vendas está desligado nesta casa.")
        elif not stock.summary(resultados)["movimentos"]:
            messages.success(request, "O stock já estava certo: nada mudou")
        else:
            _mensagem_stock(request, resultados)
        return redirect("sales:stock")
