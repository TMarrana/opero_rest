"""
Contagens físicas (Fase 14): a folha de contagem, que acerta o stock com um
ajuste por artigo, e o teórico contra real entre duas contagens.
"""
import datetime

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View

from attendance.month import month_range, next_month, previous_month
from core.mixins import StockRequiredMixin
from core.utils import parse_decimal, restaurant_scope

from . import counts
from .consumption_views import _mes
from .models import Category, Item, StockCount
from .services import register_count


def _aviso_vendas(restaurant):
    """Com o stock pelas vendas ligado, uma contagem antes de importar as
    vendas de ontem fica errada: essas vendas saem do stock depois, com a
    data delas. Devolve o último dia importado, se estiver atrasado."""
    from sales.models import SalesSettings
    from sales.reports import ultimo_dia

    if not SalesSettings.for_restaurant(restaurant).stock_enabled:
        return None
    ultimo = ultimo_dia(restaurant)
    ontem = timezone.localdate() - datetime.timedelta(days=1)
    if ultimo is None or ultimo < ontem:
        return ultimo or False
    return None


class CountSheetView(StockRequiredMixin, View):
    """A folha de contagem: o que se contou de cada artigo. Só os artigos
    preenchidos contam; os outros ficam como estão."""

    template_name = "manage/inventory/contagem.html"

    def _artigos(self, request):
        qs = restaurant_scope(request, Item.objects.filter(is_active=True)).select_related("category")
        categoria = request.GET.get("categoria") or request.POST.get("categoria") or ""
        if categoria:
            qs = qs.filter(category_id=categoria)
        if request.GET.get("negativos"):
            qs = qs.filter(current_stock__lt=0)
        return qs.order_by("category__name", "name"), categoria

    def _render(self, request, erro=None, valores=None, status=200):
        artigos, categoria = self._artigos(request)
        valores = valores or {}
        for a in artigos:
            a.valor = valores.get(a.pk, "")
        return render(
            request,
            self.template_name,
            {
                "artigos": artigos,
                "categorias": restaurant_scope(request, Category.objects.all()),
                "categoria": categoria,
                "negativos": request.GET.get("negativos", ""),
                "erro": erro,
                "vendas_atrasadas": _aviso_vendas(request.restaurant),
            },
            status=status,
        )

    def get(self, request):
        return self._render(request)

    def post(self, request):
        artigos = {i.pk: i for i in restaurant_scope(request, Item.objects.filter(is_active=True))}
        valores, contados = {}, []
        try:
            for chave, texto in request.POST.items():
                if not chave.startswith("contado_") or not texto.strip():
                    continue
                pk = int(chave.removeprefix("contado_"))
                if pk not in artigos:
                    continue
                valores[pk] = texto
                contados.append((artigos[pk], parse_decimal(texto, f"A quantidade de {artigos[pk]}")))
            if not contados:
                raise ValidationError("Escreva a quantidade contada de pelo menos um artigo.")
            agora = timezone.now()
            with transaction.atomic():
                feitas = [register_count(item=i, counted=q, user=request.user, at=agora) for i, q in contados]
        except ValidationError as exc:
            return self._render(request, erro=" ".join(exc.messages), valores=valores, status=400)
        diferentes = sum(1 for c in feitas if c.difference)
        messages.success(
            request,
            f"Contagem registada: {len(feitas)} artigo(s), {diferentes} com diferença acertada por ajuste",
        )
        return redirect("inventory:contagens")


class CountListView(StockRequiredMixin, View):
    """As contagens do mês, cada uma comparada com a anterior do mesmo
    artigo: o consumo esperado (vendas, consumos internos, quebras) contra
    o real."""

    template_name = "manage/inventory/contagens.html"

    def get(self, request):
        mes = _mes(request)
        inicio, fim = month_range(mes)
        lista = (
            restaurant_scope(request, StockCount.objects.all(), field="item__restaurant")
            .filter(counted_at__date__range=(inicio, fim))
            .select_related("item", "created_by")
            .order_by("-counted_at", "item__name")
        )
        linhas = counts.comparisons(lista)
        comparadas = [l for l in linhas if l.previous is not None]
        valores = [l.value for l in comparadas if l.value is not None]
        return render(
            request,
            self.template_name,
            {
                "mes": mes,
                "mes_anterior": previous_month(mes),
                "mes_seguinte": next_month(mes) if next_month(mes) <= timezone.localdate() else None,
                "linhas": linhas,
                "total_valor": sum(valores) if valores else None,
                "sem_custo": any(l.value is None for l in comparadas),
            },
        )
