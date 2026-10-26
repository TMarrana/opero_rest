"""
Fichas técnicas (Fase 13): lista, ficha, criar e mudar (uma versão nova de
cada vez), ficha para a cozinha e produtos do POS sem ficha. Admin, Gerente
e Responsável de stock (matriz da secção 7). As fichas são do grupo da casa
ativa; o custo e os produtos do POS são os da casa ativa.
"""
import datetime
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from accounts.models import User
from core.mixins import StockRequiredMixin
from core.utils import parse_decimal, restaurant_scope
from inventory.models import Item
from sales.models import PosProduct
from sales.templatetags.vendas import campo, campo_preco

from . import services
from .models import Recipe, RecipeProduct

LINHAS_EM_BRANCO = 5
MAX_LINHAS = 60


def _recipes(request):
    if request.restaurant is None:
        return Recipe.objects.none()
    return Recipe.objects.filter(organization_id=request.restaurant.organization_id)


def _erro(request, exc):
    messages.error(request, " ".join(exc.messages))


def _ve_vendas(request):
    return request.role in (User.Role.ADMIN, User.Role.MANAGER)


# ---- Lista -----------------------------------------------------------------


class RecipeListView(StockRequiredMixin, View):
    def get(self, request):
        q = request.GET.get("q", "").strip()
        tipo = request.GET.get("tipo", "")
        arquivadas = request.GET.get("arquivadas") == "1"
        fichas = _recipes(request).filter(is_active=not arquivadas)
        if q:
            fichas = fichas.filter(name__icontains=q)
        if tipo in Recipe.Kind.values:
            fichas = fichas.filter(kind=tipo)
        return render(
            request,
            "manage/recipes/lista.html",
            {
                "linhas": services.summaries(fichas, request.restaurant),
                "q": q,
                "tipo": tipo,
                "tipos": Recipe.Kind.choices,
                "arquivadas": arquivadas,
            },
        )


# ---- Criar e mudar ---------------------------------------------------------


def _valor_ingrediente(linha):
    if linha.preparation_id:
        return f"p:{linha.preparation_id}"
    return f"a:{linha.unit}:{linha.item_name}"


class RecipeFormView(StockRequiredMixin, View):
    """Os dados da ficha e a receita no mesmo formulário. Guardar uma receita
    diferente cria uma versão nova; os dados da ficha (nome, tipo, preço)
    mudam sem versão."""

    template_name = "manage/recipes/form.html"

    def _ficha(self, request, pk):
        return None if pk is None else get_object_or_404(_recipes(request), pk=pk)

    def _preparacoes(self, request, ficha):
        preps = _recipes(request).filter(kind=Recipe.Kind.PREPARACAO, is_active=True)
        return preps.exclude(pk=ficha.pk) if ficha else preps

    def _contexto(self, request, ficha, dados, linhas, erro=""):
        ingredientes = services.ingredient_choices(request.restaurant.organization)
        da_casa = set(services.items_by_name(request.restaurant))
        valores = {l["ing"] for l in linhas if l["ing"]}
        opcoes = [
            {"valor": f"a:{u}:{n}", "nome": n, "unidade": u, "fora": n.casefold() not in da_casa}
            for n, u in ingredientes
        ]
        # Um artigo que já está na receita e deixou de existir continua na lista.
        conhecidos = {o["valor"] for o in opcoes}
        for v in sorted(valores - conhecidos):
            if v.startswith("a:"):
                _, u, n = v.split(":", 2)
                opcoes.append({"valor": v, "nome": n, "unidade": u, "fora": True})
        return {
            "ficha": ficha,
            "dados": dados,
            "linhas": linhas,
            "n_linhas": len(linhas),
            "artigos": opcoes,
            "preparacoes": [{"valor": f"p:{r.pk}", "nome": r.name} for r in self._preparacoes(request, ficha)],
            "tipos": Recipe.Kind.choices,
            "erro": erro,
            "hoje": timezone.localdate(),
        }

    def get(self, request, pk=None):
        ficha = self._ficha(request, pk)
        produto = None
        if ficha is None:
            produto = restaurant_scope(request, PosProduct.objects.all()).filter(pk=request.GET.get("produto")).first()
            dados = {
                "nome": produto.description if produto else "",
                "tipo": Recipe.Kind.PRATO,
                "preco": "",
                "doses": "1",
                "notas": "",
                "desde": timezone.localdate().isoformat(),
                "produto": produto.pk if produto else "",
            }
            linhas = []
        else:
            versao = ficha.versions.order_by("-number").first()
            dados = {
                "nome": ficha.name,
                "tipo": ficha.kind,
                "preco": campo_preco(ficha.sale_price),
                "doses": campo(versao.portions) if versao else "1",
                "notas": versao.notes if versao else "",
                "desde": timezone.localdate().isoformat(),
            }
            linhas = [
                {"ing": _valor_ingrediente(l), "qtd": campo(l.quantity), "quebra": campo(l.waste_pct) if l.waste_pct else ""}
                for l in (versao.lines.all() if versao else [])
            ]
        linhas += [{"ing": "", "qtd": "", "quebra": ""} for _ in range(LINHAS_EM_BRANCO)]
        contexto = self._contexto(request, ficha, dados, linhas)
        contexto["produto"] = produto
        return render(request, self.template_name, contexto)

    def post(self, request, pk=None):
        ficha = self._ficha(request, pk)
        p = request.POST
        dados = {k: p.get(k, "") for k in ("nome", "tipo", "preco", "doses", "notas", "desde", "produto")}
        try:
            n = min(int(p.get("n_linhas", 0)), MAX_LINHAS)
        except ValueError:
            n = 0
        linhas = [{"ing": p.get(f"ing-{i}", ""), "qtd": p.get(f"qtd-{i}", ""), "quebra": p.get(f"quebra-{i}", "")} for i in range(n)]
        produto = None
        try:
            if dados["produto"]:
                produto = restaurant_scope(request, PosProduct.objects.all()).filter(pk=dados["produto"]).first()
            entrada = self._ler_linhas(request, ficha, linhas)
            preco = parse_decimal(dados["preco"], "O preço de venda")
            doses = parse_decimal(dados["doses"], "O número de doses")
            try:
                desde = datetime.date.fromisoformat(dados["desde"])
            except ValueError:
                raise ValidationError("Indique a data a partir da qual a receita vale.")
            with transaction.atomic():
                if ficha is None:
                    ficha = services.create_recipe(
                        organization=request.restaurant.organization,
                        name=dados["nome"],
                        kind=dados["tipo"],
                        sale_price=preco,
                        user=request.user,
                        portions=doses,
                        notes=dados["notas"],
                        lines=entrada,
                        valid_from=desde,
                    )
                    if produto is not None:
                        services.link_product(recipe=ficha, product=produto, user=request.user)
                    messages.success(request, f"Ficha {ficha.name} criada")
                else:
                    antes = (ficha.name, ficha.kind, ficha.sale_price)
                    services.save_recipe(
                        organization=ficha.organization, name=dados["nome"], kind=dados["tipo"], sale_price=preco, recipe=ficha
                    )
                    versao = services.save_version(
                        recipe=ficha, portions=doses, notes=dados["notas"], lines=entrada, user=request.user, valid_from=desde
                    )
                    if versao is not None:
                        messages.success(request, f"Receita guardada como versão {versao.number}, a partir de {versao.valid_from:%d/%m/%Y}")
                    elif antes != (ficha.name, ficha.kind, ficha.sale_price):
                        messages.success(request, "Ficha guardada. A receita ficou igual, por isso não há versão nova")
                    else:
                        messages.info(request, "Nada mudou")
        except ValidationError as exc:
            ficha = self._ficha(request, pk)
            contexto = self._contexto(request, ficha, dados, linhas, erro=" ".join(exc.messages))
            contexto["produto"] = produto
            return render(request, self.template_name, contexto, status=400)
        return redirect("recipes:ficha", pk=ficha.pk)

    def _ler_linhas(self, request, ficha, linhas):
        preparacoes = {str(r.pk): r for r in _recipes(request).filter(kind=Recipe.Kind.PREPARACAO)}
        unidades = dict(Item.Unit.choices)
        entrada = []
        for linha in linhas:
            valor = linha["ing"]
            if not valor:
                continue
            if valor.startswith("p:") and valor[2:] in preparacoes:
                ingrediente = preparacoes[valor[2:]]
                nome = ingrediente.name
            elif valor.startswith("a:") and valor.count(":") >= 2:
                _, unidade, nome = valor.split(":", 2)
                if unidade not in unidades:
                    raise ValidationError("Escolha um artigo da lista.")
                ingrediente = (nome, unidade)
            else:
                raise ValidationError("Escolha um artigo da lista.")
            entrada.append(
                (
                    ingrediente,
                    parse_decimal(linha["qtd"], f"A quantidade de {nome}"),
                    parse_decimal(linha["quebra"], f"A quebra de {nome}"),
                )
            )
        return entrada


# ---- Ficha -----------------------------------------------------------------


class RecipeDetailView(StockRequiredMixin, View):
    template_name = "manage/recipes/ficha.html"

    def get(self, request, pk):
        ficha = get_object_or_404(_recipes(request), pk=pk)
        versoes = list(ficha.versions.select_related("created_by"))
        em_vigor = ficha.current_version()
        versao = next((v for v in versoes if str(v.number) == request.GET.get("versao")), em_vigor)
        custo = services.recipe_cost(versao, request.restaurant) if versao else None
        preco, produto_preco = services.sale_price(ficha, request.restaurant)
        por_dose = custo.per_dose if custo and custo.complete else None
        ligados = list(
            RecipeProduct.objects.filter(recipe=ficha, product__restaurant=request.restaurant).select_related("product")
        )
        for l in ligados:
            l.food_cost = services.food_cost(por_dose, l.product.last_price)
        return render(
            request,
            self.template_name,
            {
                "ficha": ficha,
                "versao": versao,
                "em_vigor": em_vigor,
                "versoes": versoes,
                "custo": custo,
                "preco": preco,
                "produto_preco": produto_preco,
                "food_cost": services.food_cost(por_dose, preco),
                "ligados": ligados,
                "noutras_casas": RecipeProduct.objects.filter(recipe=ficha).exclude(product__restaurant=request.restaurant).count(),
                "por_ligar": restaurant_scope(request, PosProduct.objects.filter(recipe_link__isnull=True)),
                "usada_em": sorted(
                    {l.version.recipe for l in ficha.used_in_lines.select_related("version__recipe")}, key=lambda r: r.name
                ),
                "ve_vendas": _ve_vendas(request),
            },
        )

    def post(self, request, pk):
        ficha = get_object_or_404(_recipes(request), pk=pk)
        acao = request.POST.get("acao")
        try:
            if acao == "ligar":
                produto = get_object_or_404(restaurant_scope(request, PosProduct.objects.all()), pk=request.POST.get("produto"))
                services.link_product(recipe=ficha, product=produto, user=request.user)
                messages.success(request, f"{produto.description} ligado à ficha")
            elif acao == "desligar":
                ligacao = get_object_or_404(
                    RecipeProduct.objects.filter(recipe=ficha, product__restaurant=request.restaurant),
                    pk=request.POST.get("ligacao"),
                )
                ligacao.delete()
                messages.success(request, f"{ligacao.product.description} desligado da ficha")
            elif acao in ("arquivar", "reativar"):
                services.set_active(recipe=ficha, active=acao == "reativar")
                messages.success(request, "Ficha arquivada" if acao == "arquivar" else "Ficha reativada")
        except ValidationError as exc:
            _erro(request, exc)
        return redirect("recipes:ficha", pk=ficha.pk)


class RecipePrintView(StockRequiredMixin, View):
    """Ficha para a cozinha, por dose e para N doses. Sem preços."""

    def get(self, request, pk):
        ficha = get_object_or_404(_recipes(request), pk=pk)
        versao = ficha.current_version()
        try:
            doses = parse_decimal(request.GET.get("doses"), "As doses") or Decimal(1)
        except ValidationError:
            doses = Decimal(1)
        doses = min(max(doses, Decimal("0.5")), Decimal(1000))
        custo = services.recipe_cost(versao, request.restaurant) if versao else None
        return render(
            request,
            "manage/recipes/imprimir.html",
            {
                "ficha": ficha,
                "versao": versao,
                "doses": doses,
                "linhas": services.scaled(custo, doses) if custo else [],
            },
        )


# ---- Produtos do POS sem ficha ----------------------------------------------


class PosProductsView(StockRequiredMixin, View):
    template_name = "manage/recipes/pos.html"

    def get(self, request):
        linhas, parte = services.products_without_recipe(request.restaurant)
        return render(
            request,
            self.template_name,
            {
                "linhas": linhas,
                "parte": parte,
                "dias": services.DIAS_DE_VENDAS,
                "fichas": _recipes(request).filter(is_active=True).exclude(kind=Recipe.Kind.PREPARACAO),
                "ve_vendas": _ve_vendas(request),
                "tem_produtos": restaurant_scope(request, PosProduct.objects.all()).exists(),
            },
        )

    def post(self, request):
        produto = get_object_or_404(restaurant_scope(request, PosProduct.objects.all()), pk=request.POST.get("produto"))
        ficha = _recipes(request).filter(pk=request.POST.get("ficha")).first()
        if ficha is None:
            messages.error(request, f"Escolha a ficha de {produto.description}.")
            return redirect("recipes:pos")
        try:
            services.link_product(recipe=ficha, product=produto, user=request.user)
        except ValidationError as exc:
            _erro(request, exc)
        else:
            messages.success(request, f"{produto.description} ligado à ficha {ficha.name}")
        return redirect("recipes:pos")
