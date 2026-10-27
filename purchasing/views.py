"""
Compras (Fase 11): lista de compras, encomendas, receções e fornecedores.
Admin, Gerente e Responsável de stock (matriz da secção 7). Os fornecedores
são do grupo da casa ativa; o resto é da casa ativa.
"""
import csv
import datetime
import io

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from attendance.month import month_start, next_month, previous_month
from core import exports
from core.mixins import StockRequiredMixin
from core.utils import restaurant_scope
from inventory.models import Item

from sales.templatetags.vendas import campo_preco

from . import services
from .forms import ReceiptHeaderForm, SupplierForm
from .models import PurchaseOrder, Receipt, Supplier, SupplierItem

LINHAS_SEM_ENCOMENDA = 8


def _suppliers(request):
    if request.restaurant is None:
        return Supplier.objects.none()
    return Supplier.objects.filter(organization_id=request.restaurant.organization_id)


def _items(request):
    return restaurant_scope(request, Item.objects.filter(is_active=True)).order_by("name")


def _orders(request):
    return restaurant_scope(request, PurchaseOrder.objects.select_related("supplier"))


def _erro(request, exc):
    messages.error(request, " ".join(exc.messages))


# ---- Lista de compras ----------------------------------------------------


class ShoppingListView(StockRequiredMixin, View):
    template_name = "manage/purchasing/lista.html"

    def get(self, request):
        return render(request, self.template_name, {"grupos": services.shopping_list(request.restaurant)})

    def post(self, request):
        """Cria o rascunho da encomenda de um fornecedor com as quantidades
        escolhidas na lista."""
        fornecedor = get_object_or_404(_suppliers(request), pk=request.POST.get("fornecedor"))
        itens = {str(i.pk): i for i in _items(request)}
        try:
            linhas = [
                (itens[chave[4:]], services.parse_decimal(valor, "A quantidade"), None)
                for chave, valor in request.POST.items()
                if chave.startswith("qtd-") and chave[4:] in itens
            ]
            if not any(q for _, q, _ in linhas):
                raise ValidationError("Indique a quantidade de pelo menos um artigo.")
            encomenda = services.create_order(
                restaurant=request.restaurant, supplier=fornecedor, lines=linhas, user=request.user
            )
        except ValidationError as exc:
            _erro(request, exc)
            return redirect("purchasing:lista")
        messages.success(request, f"Encomenda {encomenda.reference} criada em rascunho")
        return redirect("purchasing:encomenda", pk=encomenda.pk)


# ---- Encomendas -----------------------------------------------------------


class OrderListView(StockRequiredMixin, View):
    def get(self, request):
        estado = request.GET.get("estado", "abertas")
        encomendas = _orders(request).annotate(n_linhas=Count("lines"))
        if estado == "abertas":
            encomendas = encomendas.filter(state__in=PurchaseOrder.OPEN_STATES)
        elif estado in PurchaseOrder.State.values:
            encomendas = encomendas.filter(state=estado)
        formato = exports.formato_pedido(request)
        if formato:
            encomendas = encomendas.prefetch_related("lines__item", "lines__receipt_lines")
            return exports.responder(formato, _tabelas_encomendas(encomendas), "encomendas")
        return render(
            request,
            "manage/purchasing/encomendas.html",
            {
                "encomendas": encomendas[:100],
                "estado": estado,
                "estados": PurchaseOrder.State.choices,
                "fornecedores": _suppliers(request).filter(is_active=True),
            },
        )


def _tabelas_encomendas(encomendas):
    """As encomendas do filtro (Fase 15) e, no Excel, as linhas numa segunda
    folha."""
    cabecalho = exports.Tabela(
        titulo="Encomendas",
        colunas=["Referência", "Fornecedor", "Estado", "Criada em", "Enviada em", "Entrega prevista", "Linhas",
                 "Total previsto", "Observações"],
        linhas=[
            [e.reference, e.supplier.name, e.get_state_display(), e.created_at, e.sent_at, e.expected_date, e.n_linhas,
             e.total(), e.notes]
            for e in encomendas
        ],
        formatos=[exports.TEXTO] * 3 + [exports.DATAHORA, exports.DATAHORA, exports.DATA, exports.NUMERO, exports.EUROS],
    )
    linhas = exports.Tabela(
        titulo="Linhas",
        colunas=["Encomenda", "Fornecedor", "Artigo", "Unidade", "Quantidade", "Preço previsto", "Total previsto", "Recebido",
                 "Por receber"],
        linhas=[
            [e.reference, e.supplier.name, l.item.name, l.item.get_unit_display(), l.quantity, l.unit_price, l.total(),
             l.received(), l.pending()]
            for e in encomendas
            for l in e.lines.all()
        ],
        formatos=[exports.TEXTO] * 4 + [exports.NUMERO, exports.EUROS, exports.EUROS, exports.NUMERO, exports.NUMERO],
    )
    return [cabecalho, linhas]


class OrderCreateView(StockRequiredMixin, View):
    """Encomenda em branco a um fornecedor, para quando não se parte da
    lista de compras."""

    def post(self, request):
        fornecedor = get_object_or_404(_suppliers(request), pk=request.POST.get("fornecedor"))
        try:
            encomenda = services.create_order(
                restaurant=request.restaurant, supplier=fornecedor, lines=[], user=request.user
            )
        except ValidationError as exc:
            _erro(request, exc)
            return redirect("purchasing:encomendas")
        return redirect("purchasing:encomenda", pk=encomenda.pk)


class OrderDetailView(StockRequiredMixin, View):
    template_name = "manage/purchasing/encomenda.html"

    def _contexto(self, request, encomenda):
        linhas = list(encomenda.lines.select_related("item"))
        for l in linhas:
            l.recebido = l.received()
            l.falta = l.pending()
        no_rascunho = {l.item_id for l in linhas}
        return {
            "encomenda": encomenda,
            "linhas": linhas,
            "texto": services.order_text(encomenda),
            "rececoes": encomenda.receipts.select_related("received_by").prefetch_related("lines__item"),
            "artigos": [i for i in _items(request) if i.pk not in no_rascunho],
            "pode_receber": encomenda.state in (PurchaseOrder.State.ENVIADA, PurchaseOrder.State.PARCIAL),
            "pode_cancelar": encomenda.state in (PurchaseOrder.State.RASCUNHO, PurchaseOrder.State.ENVIADA),
        }

    def get(self, request, pk):
        encomenda = get_object_or_404(_orders(request), pk=pk)
        return render(request, self.template_name, self._contexto(request, encomenda))

    def post(self, request, pk):
        encomenda = get_object_or_404(_orders(request), pk=pk)
        acao = request.POST.get("acao")
        try:
            if acao in ("guardar", "enviar"):
                self._guardar(request, encomenda)
            if acao == "enviar":
                services.send_order(order=encomenda, user=request.user)
                messages.success(request, f"Encomenda {encomenda.reference} marcada como enviada")
            elif acao == "cancelar":
                services.cancel_order(order=encomenda, user=request.user)
                messages.success(request, f"Encomenda {encomenda.reference} cancelada")
            elif acao == "guardar":
                messages.success(request, "Encomenda guardada")
        except ValidationError as exc:
            _erro(request, exc)
        return redirect("purchasing:encomenda", pk=encomenda.pk)

    def _guardar(self, request, encomenda):
        if encomenda.state != PurchaseOrder.State.RASCUNHO:
            return
        itens = {str(i.pk): i for i in restaurant_scope(request, Item.objects.all())}
        linhas = {}
        for l in encomenda.lines.select_related("item"):
            linhas[l.item] = (
                services.parse_decimal(request.POST.get(f"qtd-{l.item_id}"), f"A quantidade de {l.item}"),
                services.parse_decimal(request.POST.get(f"preco-{l.item_id}"), f"O preço de {l.item}"),
            )
        novo = itens.get(request.POST.get("novo_item", ""))
        if novo is not None:
            linhas[novo] = (
                services.parse_decimal(request.POST.get("novo_qtd"), f"A quantidade de {novo}"),
                services.parse_decimal(request.POST.get("novo_preco"), f"O preço de {novo}")
                or SupplierItem.objects.filter(supplier=encomenda.supplier, item=novo).values_list("last_price", flat=True).first(),
            )
            if not linhas[novo][0]:
                raise ValidationError(f"Indique a quantidade de {novo}.")
        try:
            data = datetime.date.fromisoformat(request.POST.get("expected_date", ""))
        except ValueError:
            data = None
        services.update_draft(order=encomenda, lines=linhas, notes=request.POST.get("notes", "")[:300], expected_date=data)


class OrderPrintView(StockRequiredMixin, View):
    def get(self, request, pk):
        encomenda = get_object_or_404(_orders(request), pk=pk)
        refs = {si.item_id: si.supplier_ref for si in SupplierItem.objects.filter(supplier=encomenda.supplier)}
        linhas = list(encomenda.lines.select_related("item"))
        for l in linhas:
            l.ref = refs.get(l.item_id, "")
        return render(request, "manage/purchasing/imprimir.html", {"encomenda": encomenda, "linhas": linhas})


# ---- Receções ------------------------------------------------------------


class ReceiveView(StockRequiredMixin, View):
    """Receção de uma encomenda (pk) ou sem encomenda (fornecedor no GET)."""

    template_name = "manage/purchasing/receber.html"

    def _base(self, request, pk):
        if pk is not None:
            encomenda = get_object_or_404(_orders(request), pk=pk)
            return encomenda, encomenda.supplier
        fornecedor = _suppliers(request).filter(pk=request.GET.get("fornecedor") or request.POST.get("fornecedor")).first()
        return None, fornecedor

    def _linhas(self, request, encomenda, fornecedor, dados=None):
        """As linhas do formulário, com os valores escritos se houver."""
        dados = dados or {}
        precos = {si.item_id: si.last_price for si in SupplierItem.objects.filter(supplier=fornecedor)} if fornecedor else {}
        if encomenda is not None:
            linhas = []
            for l in encomenda.lines.select_related("item"):
                falta = l.pending()
                preco = l.unit_price if l.unit_price is not None else precos.get(l.item_id)
                linhas.append(
                    {
                        "chave": l.pk,
                        "linha": l,
                        "item": l.item,
                        "encomendado": l.quantity,
                        "falta": falta,
                        "qtd": dados.get(f"qtd-{l.pk}", _texto(falta) if falta else ""),
                        "preco": dados.get(f"preco-{l.pk}", campo_preco(preco)),
                    }
                )
            return linhas
        return [
            {
                "chave": n,
                "item_id": dados.get(f"item-{n}", ""),
                "qtd": dados.get(f"qtd-{n}", ""),
                "preco": dados.get(f"preco-{n}", ""),
            }
            for n in range(LINHAS_SEM_ENCOMENDA)
        ]

    def _render(self, request, encomenda, fornecedor, form, linhas, status=200):
        if encomenda is not None and encomenda.state not in (PurchaseOrder.State.ENVIADA, PurchaseOrder.State.PARCIAL):
            messages.error(request, f"A encomenda {encomenda.reference} está {encomenda.get_state_display().lower()}.")
            return redirect("purchasing:encomenda", pk=encomenda.pk)
        artigos = list(_items(request))
        if fornecedor is not None and encomenda is None:
            do_fornecedor = set(SupplierItem.objects.filter(supplier=fornecedor).values_list("item_id", flat=True))
            artigos.sort(key=lambda i: (i.pk not in do_fornecedor, i.name))
        return render(
            request,
            self.template_name,
            {
                "encomenda": encomenda,
                "fornecedor": fornecedor,
                "fornecedores": _suppliers(request).filter(is_active=True),
                "form": form,
                "linhas": linhas,
                "artigos": artigos,
            },
            status=status,
        )

    def get(self, request, pk=None):
        encomenda, fornecedor = self._base(request, pk)
        return self._render(request, encomenda, fornecedor, ReceiptHeaderForm(), self._linhas(request, encomenda, fornecedor))

    def post(self, request, pk=None):
        encomenda, fornecedor = self._base(request, pk)
        form = ReceiptHeaderForm(request.POST)
        linhas = self._linhas(request, encomenda, fornecedor, request.POST)
        if fornecedor is None:
            messages.error(request, "Escolha o fornecedor.")
            return redirect("purchasing:rececao_nova")
        if not form.is_valid():
            return self._render(request, encomenda, fornecedor, form, linhas, status=400)
        try:
            rececao = services.receive(
                restaurant=request.restaurant,
                supplier=fornecedor,
                order=encomenda,
                lines=self._valores(request, encomenda, linhas),
                user=request.user,
                document_number=form.cleaned_data["document_number"],
                document_date=form.cleaned_data["document_date"],
                notes=form.cleaned_data["notes"],
            )
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
            return self._render(request, encomenda, fornecedor, form, linhas, status=400)
        messages.success(request, f"Receção {rececao.reference} registada")
        if encomenda is not None:
            return redirect("purchasing:encomenda", pk=encomenda.pk)
        return redirect("purchasing:rececao", pk=rececao.pk)

    def _valores(self, request, encomenda, linhas):
        valores = []
        if encomenda is not None:
            for l in linhas:
                valores.append(
                    (
                        l["item"],
                        services.parse_decimal(l["qtd"], f"A quantidade de {l['item']}"),
                        services.parse_decimal(l["preco"], f"O preço de {l['item']}"),
                        l["linha"],
                    )
                )
            return valores
        itens = {str(i.pk): i for i in _items(request)}
        for l in linhas:
            item = itens.get(str(l["item_id"]))
            qtd = services.parse_decimal(l["qtd"], "A quantidade")
            if item is None:
                if qtd:
                    raise ValidationError("Há uma quantidade numa linha sem artigo. Escolha o artigo.")
                continue
            valores.append((item, qtd, services.parse_decimal(l["preco"], f"O preço de {item}"), None))
        return valores


def _texto(valor):
    if valor is None:
        return ""
    valor = valor.normalize()
    return format(valor, "f").replace(".", ",")


def _mes_pedido(request):
    try:
        return datetime.datetime.strptime(request.GET.get("mes", ""), "%Y-%m").date()
    except ValueError:
        return month_start(datetime.date.today())


class ReceiptListView(StockRequiredMixin, View):
    """Receções do mês, por fornecedor, e a exportação das linhas em CSV."""

    def get(self, request):
        mes = _mes_pedido(request)
        linhas = list(services.month_receipts(request.restaurant, mes))
        exportar = request.GET.get("exportar")
        if exportar == "xlsx":
            return exports.xlsx_response([_tabela_rececoes(linhas)], f"compras-{mes:%Y-%m}")
        if exportar:
            # O CSV de sempre, para o contabilista (Fase 11).
            return self._csv(linhas, mes)
        rececoes = (
            restaurant_scope(request, Receipt.objects.select_related("supplier", "order", "received_by"))
            .filter(document_date__gte=mes, document_date__lt=next_month(mes))
            .prefetch_related("lines")
        )
        return render(
            request,
            "manage/purchasing/rececoes.html",
            {
                "mes": mes,
                "mes_anterior": previous_month(mes),
                "mes_seguinte": next_month(mes) if next_month(mes) <= datetime.date.today() else None,
                "por_fornecedor": services.by_supplier(linhas),
                "total": sum((l.total() or 0 for l in linhas), 0),
                "rececoes": rececoes,
                "fornecedores": _suppliers(request).filter(is_active=True),
            },
        )

    def _csv(self, linhas, mes):
        saida = io.StringIO()
        escrita = csv.writer(saida, delimiter=";")
        escrita.writerow(
            ["Data", "Fornecedor", "NIF", "Documento", "Encomenda", "Receção", "Artigo", "Quantidade", "Unidade", "Preço unitário", "Total"]
        )
        for l in linhas:
            r = l.receipt
            escrita.writerow(
                [
                    r.document_date.isoformat(),
                    r.supplier.name,
                    r.supplier.nif,
                    r.document_number,
                    r.order.reference if r.order else "",
                    r.reference,
                    l.item.name,
                    _texto(l.quantity),
                    l.item.unit,
                    _texto(l.unit_price),
                    _texto(l.total()),
                ]
            )
        resp = HttpResponse("﻿" + saida.getvalue(), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="compras-{mes:%Y-%m}.csv"'
        return resp


def _tabela_rececoes(linhas):
    return exports.Tabela(
        titulo="Receções",
        colunas=["Data", "Fornecedor", "NIF", "Documento", "Encomenda", "Receção", "Artigo", "Quantidade", "Unidade",
                 "Preço unitário", "Total"],
        linhas=[
            [l.receipt.document_date, l.receipt.supplier.name, l.receipt.supplier.nif, l.receipt.document_number,
             l.receipt.order.reference if l.receipt.order else "", l.receipt.reference, l.item.name, l.quantity,
             l.item.unit, l.unit_price, l.total()]
            for l in linhas
        ],
        formatos=[exports.DATA] + [exports.TEXTO] * 6 + [exports.NUMERO, exports.TEXTO, exports.EUROS, exports.EUROS],
    )


class ReceiptDetailView(StockRequiredMixin, View):
    def get(self, request, pk):
        rececao = get_object_or_404(
            restaurant_scope(request, Receipt.objects.select_related("supplier", "order", "received_by")), pk=pk
        )
        return render(
            request,
            "manage/purchasing/rececao.html",
            {"rececao": rececao, "linhas": rececao.lines.select_related("item", "movement")},
        )


# ---- Fornecedores --------------------------------------------------------


class SupplierListView(StockRequiredMixin, View):
    def get(self, request):
        q = request.GET.get("q", "").strip()
        fornecedores = _suppliers(request).annotate(
            n_artigos=Count("items", filter=Q(items__item__restaurant=request.restaurant), distinct=True)
        )
        if q:
            fornecedores = fornecedores.filter(Q(name__icontains=q) | Q(nif__icontains=q) | Q(contact_name__icontains=q))
        return render(
            request,
            "manage/purchasing/fornecedores.html",
            {"fornecedores": fornecedores.order_by("-is_active", "name"), "q": q},
        )


class SupplierFormView(StockRequiredMixin, View):
    template_name = "manage/purchasing/fornecedor_form.html"

    def get(self, request, pk=None):
        fornecedor = get_object_or_404(_suppliers(request), pk=pk) if pk else None
        form = SupplierForm(instance=fornecedor, organization=request.restaurant.organization)
        return render(request, self.template_name, {"form": form, "fornecedor": fornecedor})

    def post(self, request, pk=None):
        fornecedor = get_object_or_404(_suppliers(request), pk=pk) if pk else None
        form = SupplierForm(request.POST, instance=fornecedor, organization=request.restaurant.organization)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "fornecedor": fornecedor}, status=400)
        novo = form.save(commit=False)
        novo.organization = request.restaurant.organization
        novo.save()
        messages.success(request, "Fornecedor guardado" if fornecedor else "Fornecedor criado")
        return redirect("purchasing:fornecedor", pk=novo.pk)


class SupplierDetailView(StockRequiredMixin, View):
    template_name = "manage/purchasing/fornecedor.html"

    def get(self, request, pk):
        fornecedor = get_object_or_404(_suppliers(request), pk=pk)
        artigos = SupplierItem.objects.filter(supplier=fornecedor, item__restaurant=request.restaurant).select_related("item")
        ligados = set(artigos.values_list("item_id", flat=True))
        return render(
            request,
            self.template_name,
            {
                "fornecedor": fornecedor,
                "artigos": artigos,
                "por_ligar": [i for i in _items(request) if i.pk not in ligados],
                "encomendas": _orders(request).filter(supplier=fornecedor)[:10],
            },
        )

    def post(self, request, pk):
        fornecedor = get_object_or_404(_suppliers(request), pk=pk)
        acao = request.POST.get("acao")
        destino = reverse("purchasing:fornecedor", args=[fornecedor.pk])
        try:
            if acao in ("ligar", "guardar_artigo"):
                item = get_object_or_404(restaurant_scope(request, Item.objects.all()), pk=request.POST.get("item"))
                services.save_supplier_item(
                    supplier=fornecedor,
                    item=item,
                    supplier_ref=request.POST.get("supplier_ref", "").strip()[:60],
                    last_price=services.parse_decimal(request.POST.get("last_price"), "O preço"),
                    preferred=bool(request.POST.get("preferred")),
                )
                messages.success(request, f"{item} guardado")
            elif acao == "desligar":
                ligacao = get_object_or_404(
                    SupplierItem, supplier=fornecedor, item__restaurant=request.restaurant, pk=request.POST.get("ligacao")
                )
                ligacao.delete()
                messages.success(request, f"{ligacao.item} deixou de estar neste fornecedor")
            elif acao == "arquivar":
                fornecedor.is_active = False
                fornecedor.save(update_fields=["is_active", "updated_at"])
                messages.success(request, f"{fornecedor} arquivado")
            elif acao == "reativar":
                fornecedor.is_active = True
                fornecedor.save(update_fields=["is_active", "updated_at"])
                messages.success(request, f"{fornecedor} reativado")
            elif acao == "apagar":
                if fornecedor.has_history():
                    raise ValidationError("Este fornecedor tem encomendas ou receções: arquive-o em vez de o apagar.")
                fornecedor.delete()
                messages.success(request, f"{fornecedor} apagado")
                return redirect("purchasing:fornecedores")
        except ValidationError as exc:
            _erro(request, exc)
        return redirect(destino)


class ItemPricesView(StockRequiredMixin, View):
    """Histórico de preços de um artigo, por fornecedor."""

    def get(self, request, pk):
        item = get_object_or_404(restaurant_scope(request, Item.objects.all()), pk=pk)
        return render(
            request,
            "manage/purchasing/precos.html",
            {
                "item": item,
                "fornecedores": SupplierItem.objects.filter(item=item).select_related("supplier"),
                "historico": item.receipt_lines.select_related("receipt__supplier", "receipt__order").order_by(
                    "-receipt__document_date", "-receipt_id"
                )[:100],
            },
        )
