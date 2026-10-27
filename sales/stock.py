"""
Stock atualizado pelas vendas (Fase 14).

Cada produto vendido com ficha técnica dá um consumo teórico: os artigos da
versão da ficha em vigor nesse dia, com a quebra, vezes as doses vendidas.
Por casa, por dia de serviço e por artigo, sai do stock um só movimento, de
origem venda, e não um por linha de venda.

Aplicar um dia é idempotente: calcula-se o consumo teórico com as vendas que
contam agora e compara-se com o que já saiu (`SaleStockMovement`). Só a
diferença entra, como um movimento novo; o antigo nunca se edita
(invariante 2). Assim, importar o mesmo ficheiro outra vez não mexe no
stock, e uma nota de crédito ou uma fatura anulada depois devolvem o que
tinham tirado.

Os artigos ligam-se às linhas da ficha pelo nome e pela unidade, em cada
casa (catálogo por casa, secção 12). Uma linha sem artigo nesta casa, ou com
outra unidade, não tira nada e fica na lista de problemas, como os produtos
vendidos sem ficha.
"""
import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from inventory.models import StockMovement
from inventory.services import register_movement
from recipes.models import Recipe, RecipeProduct
from recipes.services import gross_quantity, items_by_name

from .models import PosProduct, SaleStockMovement, SalesDocument, SalesLine, SalesSettings

MIL = Decimal("0.001")


@dataclass
class Problem:
    """Uma razão para uma venda não ter tirado do stock o que devia."""

    kind: str  # "sem_ficha", "sem_versao", "sem_artigo", "unidade", "preparacao"
    text: str
    product: PosProduct | None = None
    recipe: Recipe | None = None
    item_name: str = ""
    quantity: Decimal = Decimal(0)


@dataclass
class DayResult:
    day: datetime.date
    consumption: dict = field(default_factory=dict)  # {artigo: quantidade}
    problems: list = field(default_factory=list)
    movements: int = 0


def _sold_by_product(restaurant, day):
    """{produto: quantidade} vendida no dia de serviço, só com os documentos
    que contam. As notas de crédito já vêm com quantidade negativa."""
    linhas = (
        SalesLine.objects.filter(document__restaurant=restaurant, document__service_date=day)
        .exclude(document__status__in=SalesDocument.EXCLUDED_STATUSES)
        .values("product")
        .annotate(q=Sum("quantity"))
    )
    return {l["product"]: l["q"] for l in linhas if l["q"]}


def theoretical(restaurant, day, *, items=None):
    """O consumo teórico de um dia de serviço numa casa: {artigo: quantidade},
    e os problemas que o deixaram incompleto."""
    items = items if items is not None else items_by_name(restaurant)
    resultado = DayResult(day=day)
    vendidos = _sold_by_product(restaurant, day)
    if not vendidos:
        return resultado
    produtos = PosProduct.objects.in_bulk(list(vendidos))
    ligacoes = {
        l.product_id: l.recipe
        for l in RecipeProduct.objects.filter(product_id__in=list(vendidos)).select_related("recipe")
    }
    consumo = defaultdict(Decimal)
    problemas = {}

    def problema(chave, **dados):
        p = problemas.get(chave)
        if p is None:
            problemas[chave] = Problem(**dados)
        else:
            p.quantity += dados.get("quantity", 0)

    def gastar(versao, doses, receita, nivel=0):
        for l in versao.lines.select_related("preparation"):
            bruta = gross_quantity(l.quantity, l.waste_pct) / versao.portions * doses
            if l.preparation_id:
                sub = l.preparation.version_on(day)
                if sub is None or nivel:
                    problema(
                        ("preparacao", l.preparation_id), kind="preparacao", recipe=l.preparation,
                        text=f"{l.preparation} não tem receita em vigor a {day:%d/%m/%Y}.",
                    )
                    continue
                gastar(sub, bruta, l.preparation, nivel=1)
                continue
            item = items.get(l.item_name.casefold())
            if item is None:
                problema(
                    ("sem_artigo", l.item_name.casefold()), kind="sem_artigo", recipe=receita, item_name=l.item_name,
                    quantity=bruta, text=f"Não há «{l.item_name}» nesta casa (ficha {receita}).",
                )
            elif item.unit != l.unit:
                problema(
                    ("unidade", item.pk), kind="unidade", recipe=receita, item_name=l.item_name, quantity=bruta,
                    text=f"A ficha {receita} tem {l.item_name} em {l.unit}, e nesta casa está em {item.unit}.",
                )
            else:
                consumo[item] += bruta

    for produto_id, quantidade in vendidos.items():
        produto = produtos[produto_id]
        receita = ligacoes.get(produto_id)
        if receita is None:
            problema(
                ("sem_ficha", produto_id), kind="sem_ficha", product=produto, quantity=quantidade,
                text=f"{produto} não tem ficha técnica.",
            )
            continue
        versao = receita.version_on(day)
        if versao is None:
            problema(
                ("sem_versao", receita.pk), kind="sem_versao", product=produto, recipe=receita, quantity=quantidade,
                text=f"A ficha {receita} só começa depois de {day:%d/%m/%Y}.",
            )
            continue
        gastar(versao, quantidade, receita)

    resultado.consumption = {i: q.quantize(MIL, ROUND_HALF_UP) for i, q in consumo.items()}
    resultado.problems = list(problemas.values())
    return resultado


def applied(restaurant, day):
    """{artigo_id: quantidade} que as vendas do dia já tiraram do stock."""
    return {
        r["item"]: r["q"]
        for r in SaleStockMovement.objects.filter(restaurant=restaurant, service_date=day)
        .values("item")
        .annotate(q=Sum("quantity"))
    }


def _fim_do_dia(day, cutoff_hour):
    """O fim do dia de serviço, que acaba à hora de corte do dia seguinte.
    Um dia que ainda não acabou fica com a hora de agora."""
    fim = timezone.make_aware(
        datetime.datetime.combine(day + datetime.timedelta(days=1), datetime.time(cutoff_hour))
    ) - datetime.timedelta(seconds=1)
    return min(fim, timezone.now())


def apply_day(*, restaurant, day, user, sales_import=None, settings_=None, items=None):
    """Acerta o stock pelas vendas de um dia: só entra a diferença entre o
    consumo teórico de agora e o que já saiu."""
    regras = settings_ or SalesSettings.for_restaurant(restaurant)
    resultado = theoretical(restaurant, day, items=items)
    ja = applied(restaurant, day)
    por_id = {i.pk: i for i in resultado.consumption}
    alvo = {i.pk: q for i, q in resultado.consumption.items()}
    if ja:
        from inventory.models import Item

        por_id.update(Item.objects.in_bulk([pk for pk in ja if pk not in por_id]))
    quando = _fim_do_dia(day, regras.day_cutoff_hour)
    referencia = f"SAF-T {sales_import.pk}" if sales_import is not None else "Vendas"
    with transaction.atomic():
        for item_pk in sorted(set(alvo) | set(ja)):
            diferenca = alvo.get(item_pk, Decimal(0)) - ja.get(item_pk, Decimal(0))
            if not diferenca:
                continue
            acerto = item_pk in ja
            movimento = register_movement(
                item=por_id[item_pk],
                movement_type=StockMovement.Type.SAIDA if diferenca > 0 else StockMovement.Type.ENTRADA,
                quantity=abs(diferenca),
                user=user,
                occurred_at=quando,
                reason=f"Vendas de {day:%d/%m/%Y}" + (" (acerto)" if acerto else ""),
                reference=referencia,
                origin=StockMovement.Origin.VENDA,
            )
            SaleStockMovement.objects.create(
                restaurant=restaurant, service_date=day, item_id=item_pk, quantity=diferenca,
                movement=movimento, sales_import=sales_import,
            )
            resultado.movements += 1
    return resultado


def apply_days(*, restaurant, days, user, sales_import=None):
    """Aplica os dias indicados, se a casa tiver o stock pelas vendas ligado,
    a partir do dia de início. Devolve a lista de DayResult (vazia, se
    desligado)."""
    regras = SalesSettings.for_restaurant(restaurant)
    if not regras.stock_enabled or regras.stock_from is None:
        return []
    items = items_by_name(restaurant)
    return [
        apply_day(restaurant=restaurant, day=d, user=user, sales_import=sales_import, settings_=regras, items=items)
        for d in sorted(days)
        if d >= regras.stock_from
    ]


def apply_since(*, restaurant, user):
    """Ao ligar, ou ao mudar o dia de início: aplica todos os dias de
    serviço já importados a partir desse dia."""
    regras = SalesSettings.for_restaurant(restaurant)
    if not regras.stock_enabled or regras.stock_from is None:
        return []
    dias = (
        SalesDocument.objects.filter(restaurant=restaurant, service_date__gte=regras.stock_from)
        .values_list("service_date", flat=True)
        .distinct()
    )
    return apply_days(restaurant=restaurant, days=set(dias), user=user)


def summary(resultados):
    """Totais para a mensagem da importação: movimentos e problemas,
    juntando os dias."""
    problemas = {}
    for r in resultados:
        for p in r.problems:
            chave = (p.kind, p.product.pk if p.product else None, p.recipe.pk if p.recipe else None, p.item_name)
            if chave in problemas:
                problemas[chave].quantity += p.quantity
            else:
                problemas[chave] = Problem(**{**p.__dict__})
    return {
        "movimentos": sum(r.movements for r in resultados),
        "dias": len(resultados),
        "problemas": sorted(problemas.values(), key=lambda p: (p.kind != "sem_artigo", -abs(p.quantity))),
    }


def problems_since(restaurant, since, until=None):
    """Os problemas dos dias aplicados num período, para o ecrã Vendas →
    Stock. Recalcula o teórico de cada dia: não grava nada."""
    until = until or timezone.localdate()
    items = items_by_name(restaurant)
    dias = (
        SalesDocument.objects.filter(restaurant=restaurant, service_date__range=(since, until))
        .values_list("service_date", flat=True)
        .distinct()
    )
    return summary([theoretical(restaurant, d, items=items) for d in sorted(set(dias))])
