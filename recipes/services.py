"""
Fichas técnicas (Fase 13): criar e mudar fichas, com versões; custo por dose
em cada casa; ligação aos produtos do POS.

Uma linha liga-se ao artigo da casa com o mesmo nome (sem contar maiúsculas)
e a mesma unidade. Sem ele, ou sem custo, a linha fica assinalada e o custo
da ficha fica incompleto.
"""
import datetime
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from inventory.models import Item
from sales.models import PosProduct, SalesDocument, SalesLine

from .models import Recipe, RecipeLine, RecipeProduct, RecipeVersion

CENT = Decimal("0.01")
MIL = Decimal("0.001")
DIAS_DE_VENDAS = 90


# ---- Ingredientes ----------------------------------------------------------


def ingredient_choices(organization):
    """Os artigos ativos das casas do grupo, como (nome, unidade), sem repetir
    o mesmo nome na mesma unidade."""
    vistos = {}
    for nome, unidade in Item.objects.filter(
        restaurant__organization=organization, restaurant__is_active=True, is_active=True
    ).values_list("name", "unit"):
        vistos.setdefault((nome.casefold(), unidade), (nome, unidade))
    return sorted(vistos.values(), key=lambda t: (t[0].casefold(), t[1]))


def items_by_name(restaurant):
    """{nome em minúsculas: artigo}, com os artigos da casa."""
    return {i.name.casefold(): i for i in Item.objects.filter(restaurant=restaurant)}


def gross_quantity(quantity, waste_pct):
    """A quantidade bruta, que sai do stock: com 20 % de quebra, 200 g limpos
    pedem 250 g."""
    if not waste_pct:
        return Decimal(quantity)
    return (Decimal(quantity) / (1 - Decimal(waste_pct) / 100)).quantize(MIL, ROUND_HALF_UP)


# ---- Criar e mudar ---------------------------------------------------------


def save_recipe(*, organization, name, kind, sale_price=None, recipe=None):
    """Cria ou muda os dados da ficha que não têm versão: o nome, o tipo e o
    preço de referência. Não grava as linhas (`save_version`)."""
    name = " ".join((name or "").split())
    if not name:
        raise ValidationError("Indique o nome da ficha.")
    if kind not in Recipe.Kind.values:
        raise ValidationError("Escolha o tipo da ficha.")
    repetida = Recipe.objects.filter(organization=organization, name__iexact=name)
    if recipe is not None:
        repetida = repetida.exclude(pk=recipe.pk)
    if repetida.exists():
        raise ValidationError(f"Já há uma ficha «{name}» no grupo.")
    if recipe is not None and recipe.kind != kind:
        if recipe.kind == Recipe.Kind.PREPARACAO and recipe.used_in_lines.exists():
            raise ValidationError(f"{recipe} entra noutras fichas, por isso continua a ser uma preparação.")
        if kind == Recipe.Kind.PREPARACAO:
            atual = recipe.versions.order_by("-number").first()
            if atual and atual.lines.filter(preparation__isnull=False).exists():
                raise ValidationError("Uma preparação não leva outras preparações. Tire-as primeiro da receita.")
            if recipe.products.exists():
                raise ValidationError("Uma preparação não se vende. Desligue primeiro os produtos do POS.")
    if recipe is None:
        recipe = Recipe(organization=organization)
    recipe.name, recipe.kind, recipe.sale_price = name, kind, sale_price
    recipe.save()
    return recipe


def _clean_lines(recipe, kind, lines):
    """Valida as linhas, dadas como (ingrediente, quantidade, quebra). O
    ingrediente é uma preparação (`Recipe`) ou um artigo como (nome, unidade).
    As linhas sem ingrediente ou sem quantidade ficam de fora."""
    limpas, vistos = [], set()
    for ingrediente, quantidade, quebra in lines:
        if ingrediente is None or not quantidade:
            continue
        quebra = Decimal(quebra or 0)
        if isinstance(ingrediente, Recipe):
            nome = ingrediente.name
            if ingrediente.organization_id != recipe.organization_id:
                raise ValidationError(f"{nome} não é uma ficha deste grupo.")
            if ingrediente.pk == recipe.pk:
                raise ValidationError("Uma ficha não pode entrar nela própria.")
            if ingrediente.kind != Recipe.Kind.PREPARACAO:
                raise ValidationError(f"{nome} não é uma preparação.")
            if kind == Recipe.Kind.PREPARACAO:
                raise ValidationError(f"Uma preparação não leva outras preparações: tire {nome} da receita.")
            chave = ("p", ingrediente.pk)
            linha = RecipeLine(preparation=ingrediente)
        else:
            nome, unidade = " ".join(ingrediente[0].split()), ingrediente[1]
            if not nome or unidade not in Item.Unit.values:
                raise ValidationError("Escolha um artigo da lista.")
            chave = ("a", nome.casefold())
            linha = RecipeLine(item_name=nome, unit=unidade)
        if not 0 <= quebra < 100:
            raise ValidationError(f"A quebra de {nome} tem de ser de 0 a 99 %.")
        if chave in vistos:
            raise ValidationError(f"{nome} aparece duas vezes. Junte as quantidades numa só linha.")
        vistos.add(chave)
        linha.quantity, linha.waste_pct = Decimal(quantidade), quebra
        limpas.append(linha)
    return limpas


def _assinatura(portions, notes, linhas):
    return (
        Decimal(portions).normalize(),
        (notes or "").strip(),
        [
            (l.preparation_id, l.item_name.casefold(), l.unit, Decimal(l.quantity).normalize(), Decimal(l.waste_pct).normalize())
            for l in linhas
        ],
    )


def save_version(*, recipe, portions, notes, lines, user, valid_from=None):
    """Grava a receita como uma versão nova, a valer a partir de `valid_from`
    (hoje, por omissão). Se nada mudou face à última versão, não cria nada e
    devolve None. As versões antigas não se mudam."""
    valid_from = valid_from or timezone.localdate()
    if portions is None or Decimal(portions) <= 0:
        raise ValidationError("O número de doses tem de ser maior que zero.")
    linhas = _clean_lines(recipe, recipe.kind, lines)
    ultima = recipe.versions.order_by("-number").first()
    if ultima is not None:
        data = recipe.versions.aggregate(d=Max("valid_from"))["d"]
        if valid_from < data:
            raise ValidationError(
                f"A versão nova tem de valer a partir de {data:%d/%m/%Y} ou depois, o dia em que começa a última."
            )
        if _assinatura(portions, notes, linhas) == _assinatura(ultima.portions, ultima.notes, ultima.lines.all()):
            return None
    with transaction.atomic():
        versao = RecipeVersion.objects.create(
            recipe=recipe,
            number=(ultima.number + 1) if ultima else 1,
            valid_from=valid_from,
            portions=Decimal(portions),
            notes=(notes or "").strip(),
            created_by=user,
        )
        for l in linhas:
            l.version = versao
        RecipeLine.objects.bulk_create(linhas)
    return versao


def create_recipe(*, organization, name, kind, user, portions=1, notes="", lines=(), sale_price=None, valid_from=None):
    """Ficha nova, com a primeira versão. Tudo ou nada."""
    with transaction.atomic():
        recipe = save_recipe(organization=organization, name=name, kind=kind, sale_price=sale_price)
        save_version(recipe=recipe, portions=portions, notes=notes, lines=lines, user=user, valid_from=valid_from)
    return recipe


def set_active(*, recipe, active):
    if not active and recipe.used_in_lines.filter(version__recipe__is_active=True).exists():
        usada = recipe.used_in_lines.filter(version__recipe__is_active=True).first().version.recipe
        raise ValidationError(f"{recipe} entra na ficha {usada}. Tire-a de lá antes de a arquivar.")
    recipe.is_active = active
    recipe.save(update_fields=["is_active", "updated_at"])


# ---- Custo -----------------------------------------------------------------


@dataclass
class CostLine:
    line: RecipeLine
    gross: Decimal
    item: Item | None = None
    unit_cost: Decimal | None = None
    cost: Decimal | None = None
    problem: str = ""


@dataclass
class Cost:
    version: RecipeVersion
    lines: list = field(default_factory=list)

    @property
    def priced(self):
        return any(l.cost is not None for l in self.lines)

    @property
    def complete(self):
        return bool(self.lines) and all(l.cost is not None for l in self.lines)

    @property
    def total(self):
        """A soma das linhas com custo. Incompleta, é um mínimo; sem nenhuma
        linha com custo, não há."""
        if not self.priced:
            return None
        return sum((l.cost for l in self.lines if l.cost is not None), Decimal(0)).quantize(CENT, ROUND_HALF_UP)

    def per_dose_exact(self):
        soma = sum((l.cost for l in self.lines if l.cost is not None), Decimal(0))
        return soma / self.version.portions

    @property
    def per_dose(self):
        if not self.priced:
            return None
        return self.per_dose_exact().quantize(CENT, ROUND_HALF_UP)

    @property
    def problems(self):
        return [l for l in self.lines if l.problem]


def recipe_cost(version, restaurant, *, day=None, items=None, _nivel=0):
    """O custo de uma versão numa casa, com o `reference_cost` atual dos
    artigos de lá. Numa preparação entra o custo por dose da versão dela em
    vigor no mesmo dia (hoje, sem `day`)."""
    items = items if items is not None else items_by_name(restaurant)
    custo = Cost(version=version)
    for l in version.lines.select_related("preparation"):
        c = CostLine(line=l, gross=gross_quantity(l.quantity, l.waste_pct))
        if l.preparation_id:
            prep = l.preparation
            sub = prep.version_on(day) if day else prep.current_version()
            if sub is None or _nivel:
                c.problem = "preparação sem receita"
            else:
                sub_custo = recipe_cost(sub, restaurant, day=day, items=items, _nivel=1)
                if not sub_custo.complete:
                    c.problem = "a preparação tem linhas sem custo"
                else:
                    c.unit_cost = sub_custo.per_dose_exact()
        else:
            item = items.get(l.item_name.casefold())
            if item is None:
                c.problem = "não há este artigo nesta casa"
            elif item.unit != l.unit:
                c.item, c.problem = item, f"nesta casa está em {item.unit}"
            elif item.reference_cost is None:
                c.item, c.problem = item, "sem custo"
            else:
                c.item, c.unit_cost = item, item.reference_cost
        if c.unit_cost is not None:
            c.cost = (c.gross * c.unit_cost).quantize(Decimal("0.0001"), ROUND_HALF_UP)
        custo.lines.append(c)
    return custo


def sale_price(recipe, restaurant):
    """(preço sem IVA, produto do POS) de uma dose nesta casa: o do produto
    ligado vendido mais recentemente; sem ele, o preço de referência da ficha
    e None."""
    produto = (
        PosProduct.objects.filter(recipe_link__recipe=recipe, restaurant=restaurant, last_price__isnull=False)
        .order_by("-last_price_at", "-pk")
        .first()
    )
    if produto is not None:
        return produto.last_price, produto
    return recipe.sale_price, None


def food_cost(cost_per_dose, price):
    """O custo em percentagem do preço sem IVA, com uma casa decimal."""
    if cost_per_dose is None or not price:
        return None
    return (Decimal(cost_per_dose) / Decimal(price) * 100).quantize(Decimal("0.1"), ROUND_HALF_UP)


def summaries(recipes, restaurant):
    """Uma linha por ficha para a lista: a versão em vigor, o custo nesta casa,
    o preço e o food cost."""
    items = items_by_name(restaurant)
    linhas = []
    for r in recipes:
        versao = r.current_version()
        custo = recipe_cost(versao, restaurant, items=items) if versao else None
        preco, produto = sale_price(r, restaurant) if r.kind != Recipe.Kind.PREPARACAO else (None, None)
        linhas.append(
            {
                "recipe": r,
                "version": versao,
                "cost": custo,
                "price": preco,
                "product": produto,
                "food_cost": food_cost(custo.per_dose if custo and custo.complete else None, preco),
            }
        )
    return linhas


def scaled(cost, doses):
    """As linhas para N doses, para a ficha da cozinha."""
    fator = Decimal(doses) / cost.version.portions
    return [
        {
            "line": c.line,
            "net": (c.line.quantity * fator).quantize(MIL, ROUND_HALF_UP),
            "gross": (c.gross * fator).quantize(MIL, ROUND_HALF_UP),
        }
        for c in cost.lines
    ]


# ---- POS -------------------------------------------------------------------


def link_product(*, recipe, product, user):
    if product.restaurant.organization_id != recipe.organization_id:
        raise ValidationError(f"{product} é de uma casa de outro grupo.")
    if recipe.kind == Recipe.Kind.PREPARACAO:
        raise ValidationError("Uma preparação não se vende: ligue o produto ao prato ou à bebida.")
    if not recipe.is_active:
        raise ValidationError(f"A ficha {recipe} está arquivada.")
    atual = RecipeProduct.objects.filter(product=product).select_related("recipe").first()
    if atual is not None:
        if atual.recipe_id == recipe.pk:
            return atual
        raise ValidationError(f"{product} já está ligado à ficha {atual.recipe}. Desligue-o primeiro.")
    return RecipeProduct.objects.create(recipe=recipe, product=product, created_by=user)


def sales_by_product(restaurant, days=DIAS_DE_VENDAS):
    """{produto: (quantidade, valor sem IVA)} dos últimos `days` dias, só com
    os documentos que contam."""
    desde = timezone.localdate() - datetime.timedelta(days=days)
    linhas = (
        SalesLine.objects.filter(document__restaurant=restaurant, document__service_date__gte=desde)
        .exclude(document__status__in=SalesDocument.EXCLUDED_STATUSES)
        .values("product")
        .annotate(q=Sum("quantity"), v=Sum("net_amount"))
    )
    return {l["product"]: (l["q"], l["v"]) for l in linhas}


def products_without_recipe(restaurant, days=DIAS_DE_VENDAS):
    """Os produtos do POS da casa sem ficha, do que mais pesou nas vendas dos
    últimos `days` dias para o que menos pesou. Devolve (linhas, parte das
    vendas sem ficha em %)."""
    vendas = sales_by_product(restaurant, days)
    total = sum((v for _, v in vendas.values()), Decimal(0))
    linhas = []
    for p in PosProduct.objects.filter(restaurant=restaurant, recipe_link__isnull=True):
        quantidade, valor = vendas.get(p.pk, (Decimal(0), Decimal(0)))
        peso = (valor / total * 100).quantize(Decimal("0.1"), ROUND_HALF_UP) if total else None
        linhas.append({"product": p, "quantity": quantidade, "value": valor, "share": peso})
    linhas.sort(key=lambda l: (-l["value"], l["product"].description.casefold()))
    sem_ficha = sum((l["value"] for l in linhas), Decimal(0))
    parte = (sem_ficha / total * 100).quantize(Decimal("0.1"), ROUND_HALF_UP) if total else None
    return linhas, parte
