import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import F, ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import TemplateView

from core.mixins import StockRequiredMixin
from core.models import Restaurant
from core.utils import restaurant_scope

from .forms import CategoryForm, ItemForm, MovementForm
from .models import Category, Item, StockMovement
from .services import register_movement


def _restaurant_for(user):
    return user.restaurant or Restaurant.objects.first()


def _toast(response, texto, tom="sucesso"):
    response["HX-Trigger"] = json.dumps({"toast": {"texto": texto, "tom": tom}})
    return response


def _contador_baixo(user):
    return (
        restaurant_scope(user, Item.objects.filter(is_active=True))
        .filter(current_stock__lte=F("minimum_stock"))
        .count()
    )


class ItemListView(StockRequiredMixin, TemplateView):
    template_name = "manage/inventory/lista.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = restaurant_scope(self.request.user, Item.objects.select_related("category"))
        q = self.request.GET.get("q", "").strip()
        categoria = self.request.GET.get("categoria", "")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(notes__icontains=q))
        if categoria:
            qs = qs.filter(category_id=categoria)
        if self.request.GET.get("baixo"):
            qs = qs.filter(current_stock__lte=F("minimum_stock"))
        ctx["items"] = qs
        ctx["categorias"] = restaurant_scope(self.request.user, Category.objects.all())
        ctx["contador_baixo"] = _contador_baixo(self.request.user)
        ctx["filtros"] = {"q": q, "categoria": categoria, "baixo": self.request.GET.get("baixo", "")}
        return ctx

    def get(self, request, *args, **kwargs):
        # Pedidos HTMX (pesquisa/filtros) recebem só o fragmento da tabela.
        if request.headers.get("HX-Request"):
            return render(request, "partials/inventory/tabela_items.html", self.get_context_data())
        return super().get(request, *args, **kwargs)


class ItemFormView(StockRequiredMixin, View):
    """Criação e edição de artigos numa página simples."""

    def _get_item(self, request, pk):
        if pk is None:
            return None
        return get_object_or_404(restaurant_scope(request.user, Item.objects.all()), pk=pk)

    def get(self, request, pk=None):
        item = self._get_item(request, pk)
        form = ItemForm(instance=item, restaurant=_restaurant_for(request.user))
        return render(request, "manage/inventory/form.html", {"form": form, "item": item})

    def post(self, request, pk=None):
        item = self._get_item(request, pk)
        restaurant = _restaurant_for(request.user)
        if restaurant is None:
            messages.error(request, "Ainda não há restaurante configurado. Crie-o no admin primeiro.")
            return redirect("inventory:lista")
        form = ItemForm(request.POST, instance=item, restaurant=restaurant)
        if not form.is_valid():
            return render(request, "manage/inventory/form.html", {"form": form, "item": item})
        novo = form.save(commit=False)
        novo.restaurant = restaurant
        novo.save()
        messages.success(request, "Artigo guardado" if item else "Artigo criado")
        return redirect("inventory:lista")


class MovementCreateView(StockRequiredMixin, View):
    """GET: fragmento do modal com o formulário. POST: regista via serviço
    e devolve a linha atualizada + contador (OOB) + toast."""

    _TOAST = {"ENTRADA": "Entrada registada", "SAIDA": "Saída registada"}

    def _get_item(self, request, pk):
        return get_object_or_404(
            restaurant_scope(request.user, Item.objects.select_related("category")), pk=pk
        )

    def get(self, request, pk):
        item = self._get_item(request, pk)
        return render(request, "partials/inventory/movimento_form.html", {"form": MovementForm(), "item": item})

    def post(self, request, pk):
        item = self._get_item(request, pk)
        form = MovementForm(request.POST)
        if form.is_valid():
            try:
                register_movement(
                    item=item,
                    movement_type=form.cleaned_data["movement_type"],
                    quantity=form.cleaned_data["quantity"],
                    user=request.user,
                    occurred_at=form.cleaned_data["occurred_at"],
                    reason=form.cleaned_data["reason"],
                    reference=form.cleaned_data["reference"],
                )
            except ValidationError as exc:
                form.add_error(None, exc.messages[0])
        if form.errors:
            resp = render(request, "partials/inventory/movimento_form.html", {"form": form, "item": item})
            resp["HX-Retarget"] = "#modal-slot"
            resp["HX-Reswap"] = "innerHTML"
            return resp
        item.refresh_from_db()
        resp = render(
            request,
            "partials/inventory/pos_movimento.html",
            {"item": item, "contador_baixo": _contador_baixo(request.user)},
        )
        texto = self._TOAST.get(form.cleaned_data["movement_type"], "Ajuste registado")
        return _toast(resp, texto)


class HistoryView(StockRequiredMixin, TemplateView):
    template_name = "manage/inventory/historico.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = restaurant_scope(
            self.request.user,
            StockMovement.objects.select_related("item", "created_by"),
            field="item__restaurant",
        )
        artigo = self.request.GET.get("artigo", "")
        de = parse_date(self.request.GET.get("de", "") or "")
        ate = parse_date(self.request.GET.get("ate", "") or "")
        if artigo:
            qs = qs.filter(item_id=artigo)
        if de:
            qs = qs.filter(occurred_at__date__gte=de)
        if ate:
            qs = qs.filter(occurred_at__date__lte=ate)
        ctx["movimentos"] = qs[:200]
        ctx["items"] = restaurant_scope(self.request.user, Item.objects.all())
        ctx["filtros"] = {
            "artigo": artigo,
            "de": self.request.GET.get("de", ""),
            "ate": self.request.GET.get("ate", ""),
        }
        return ctx

    def get(self, request, *args, **kwargs):
        if request.headers.get("HX-Request"):
            return render(request, "partials/inventory/rail_historico.html", self.get_context_data())
        return super().get(request, *args, **kwargs)


class CategoryListView(StockRequiredMixin, View):
    def _render(self, request, form):
        categorias = restaurant_scope(request.user, Category.objects.all()).prefetch_related("items")
        return render(request, "manage/inventory/categorias.html", {"categorias": categorias, "form": form})

    def get(self, request):
        return self._render(request, CategoryForm())

    def post(self, request):
        restaurant = _restaurant_for(request.user)
        if restaurant is None:
            messages.error(request, "Ainda não há restaurante configurado. Crie-o no admin primeiro.")
            return redirect("inventory:categorias")
        form = CategoryForm(request.POST)
        if form.is_valid():
            duplicada = (
                restaurant_scope(request.user, Category.objects.all())
                .filter(name__iexact=form.cleaned_data["name"])
                .exists()
            )
            if duplicada:
                form.add_error("name", "Já existe uma categoria com esse nome.")
            else:
                categoria = form.save(commit=False)
                categoria.restaurant = restaurant
                categoria.save()
                messages.success(request, "Categoria criada")
                return redirect("inventory:categorias")
        return self._render(request, form)


class CategoryUpdateView(StockRequiredMixin, View):
    def _get(self, request, pk):
        return get_object_or_404(restaurant_scope(request.user, Category.objects.all()), pk=pk)

    def get(self, request, pk):
        categoria = self._get(request, pk)
        form = CategoryForm(instance=categoria)
        return render(request, "manage/inventory/categoria_form.html", {"form": form, "categoria": categoria})

    def post(self, request, pk):
        categoria = self._get(request, pk)
        form = CategoryForm(request.POST, instance=categoria)
        if form.is_valid():
            duplicada = (
                restaurant_scope(request.user, Category.objects.exclude(pk=pk))
                .filter(name__iexact=form.cleaned_data["name"])
                .exists()
            )
            if duplicada:
                form.add_error("name", "Já existe uma categoria com esse nome.")
            else:
                form.save()
                messages.success(request, "Categoria guardada")
                return redirect("inventory:categorias")
        return render(request, "manage/inventory/categoria_form.html", {"form": form, "categoria": categoria})


class CategoryDeleteView(StockRequiredMixin, View):
    def post(self, request, pk):
        categoria = get_object_or_404(restaurant_scope(request.user, Category.objects.all()), pk=pk)
        try:
            categoria.delete()
            messages.success(request, "Categoria eliminada")
        except ProtectedError:
            messages.error(
                request,
                f"Não é possível eliminar a categoria «{categoria.name}»: tem artigos associados. "
                "Mova primeiro os artigos para outra categoria.",
            )
        return redirect("inventory:categorias")
