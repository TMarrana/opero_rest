"""
Contas da Análise (Fase 15). Cruzam módulos numa casa e num período, e os
totais têm de bater com os ecrãs de cada módulo: as vendas e as horas vêm de
`sales.reports.por_dia`, o mesmo do ecrã Vendas; os consumos, das mesmas
linhas do mapa do mês.

O food cost é teórico: o custo das fichas técnicas dos produtos vendidos, ao
custo de referência atual dos artigos, face às vendas sem IVA desses
produtos. Os produtos sem ficha, ou com ficha sem custo completo, ficam de
fora e a cobertura diz que parte das vendas entrou na conta.
"""
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, Sum

from inventory.models import ConsumptionLine, InternalConsumption
from recipes.models import RecipeProduct
from recipes.services import items_by_name, recipe_cost
from sales import reports as vendas
from sales.models import SalesLine

ZERO = Decimal(0)
CENT = Decimal("0.01")
DECIMA = Decimal("0.1")


def _pct(parte, todo):
    if parte is None or not todo:
        return None
    return (Decimal(parte) / Decimal(todo) * 100).quantize(DECIMA, ROUND_HALF_UP)


@dataclass
class Produto:
    code: str
    description: str
    group: str
    quantity: Decimal
    sales: Decimal
    recipe: object = None
    cost_per_dose: Decimal | None = None
    incomplete: bool = False

    @property
    def unit_price(self):
        return (self.sales / self.quantity).quantize(CENT, ROUND_HALF_UP) if self.quantity else None

    @property
    def cost(self):
        if self.cost_per_dose is None:
            return None
        return (self.cost_per_dose * self.quantity).quantize(CENT, ROUND_HALF_UP)

    @property
    def margin(self):
        return None if self.cost is None else self.sales - self.cost

    @property
    def food_cost(self):
        return _pct(self.cost, self.sales) if self.sales > 0 else None


def produtos(restaurant, inicio, fim):
    """Vendas por produto com o custo teórico da ficha: a versão em vigor no
    último dia do período, ao custo de referência atual."""
    linhas = (
        SalesLine.objects.filter(document__in=vendas.documentos(restaurant, inicio, fim))
        .values("product", "product__code", "product__description", "product__group")
        .annotate(q=Sum("quantity"), v=Sum("net_amount"))
        .order_by("-v", "product__description")
    )
    ligacoes = {
        l.product_id: l.recipe
        for l in RecipeProduct.objects.filter(product__restaurant=restaurant).select_related("recipe")
    }
    items = items_by_name(restaurant)
    custos = {}
    resultado = []
    for l in linhas:
        p = Produto(
            code=l["product__code"],
            description=l["product__description"],
            group=l["product__group"],
            quantity=Decimal(l["q"] or 0).quantize(Decimal("0.001")).normalize(),
            sales=Decimal(l["v"] or 0).quantize(CENT),
        )
        receita = ligacoes.get(l["product"])
        if receita is not None:
            p.recipe = receita
            if receita.pk not in custos:
                versao = receita.version_on(fim) or receita.current_version()
                custo = recipe_cost(versao, restaurant, day=fim, items=items) if versao else None
                custos[receita.pk] = (
                    custo.per_dose_exact() if custo is not None and custo.complete else None,
                    custo is None or not custo.complete,
                )
            p.cost_per_dose, p.incomplete = custos[receita.pk]
        resultado.append(p)
    return resultado


@dataclass
class Indicadores:
    restaurant: object
    vendas: Decimal
    documentos: int
    ticket: Decimal | None
    horas: object  # timedelta ou None
    dias_previstos: int
    por_hora: Decimal | None
    custo_pessoal: Decimal | None
    custo_teorico: Decimal
    vendas_com_custo: Decimal
    consumos: Decimal
    consumos_sem_custo: int
    refeicoes: int
    por_dia: list = field(default_factory=list)
    produtos: list = field(default_factory=list)

    @property
    def food_cost(self):
        return _pct(self.custo_teorico, self.vendas_com_custo)

    @property
    def cobertura(self):
        """Que parte das vendas tem custo teórico."""
        return _pct(self.vendas_com_custo, self.vendas)

    @property
    def margem(self):
        """A margem teórica dos produtos com custo."""
        return self.vendas_com_custo - self.custo_teorico


def indicadores(restaurant, inicio, fim):
    linhas, totais = vendas.por_dia(restaurant, inicio, fim)
    lista = produtos(restaurant, inicio, fim)
    com_custo = [p for p in lista if p.cost is not None]
    consumo = ConsumptionLine.objects.filter(
        consumption__restaurant=restaurant,
        consumption__consumed_on__range=(inicio, fim),
        consumption__cancelled_at__isnull=True,
    ).aggregate(valor=Sum("value"), sem_custo=Count("pk", filter=None) - Count("value"))
    refeicoes = InternalConsumption.objects.filter(
        restaurant=restaurant,
        consumed_on__range=(inicio, fim),
        cancelled_at__isnull=True,
        reason=InternalConsumption.Reason.REFEICAO,
    ).count()
    return Indicadores(
        restaurant=restaurant,
        vendas=totais["total"],
        documentos=totais["vendas"],
        ticket=totais["ticket"],
        horas=totais["horas"],
        dias_previstos=sum(1 for l in linhas if l["previstas"]),
        por_hora=totais["por_hora"],
        custo_pessoal=totais["custo_pessoal"],
        custo_teorico=sum((p.cost for p in com_custo), ZERO),
        vendas_com_custo=sum((p.sales for p in com_custo), ZERO),
        consumos=Decimal(consumo["valor"] or 0).quantize(CENT),
        consumos_sem_custo=consumo["sem_custo"] or 0,
        refeicoes=refeicoes,
        por_dia=linhas,
        produtos=lista,
    )
