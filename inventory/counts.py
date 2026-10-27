"""
Contagens físicas e teórico contra real (Fase 14).

Entre duas contagens de um artigo, o consumo esperado é o que os movimentos
dizem que saiu: as vendas (pelas fichas técnicas), os consumos internos e as
quebras registadas à mão. A diferença na contagem seguinte é o que saiu sem
ficar registado: desperdício, porções mal servidas ou fichas erradas.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q, Sum

from .models import StockCount, StockMovement

CENT = Decimal("0.01")


@dataclass
class CountComparison:
    count: StockCount
    previous: StockCount | None
    sales: Decimal = Decimal(0)
    consumption: Decimal = Decimal(0)
    waste: Decimal = Decimal(0)

    @property
    def expected(self):
        return self.sales + self.consumption + self.waste

    @property
    def difference(self):
        """Contado menos registado: negativo é o que faltou."""
        return self.count.difference

    @property
    def real(self):
        """O que saiu de facto: o esperado mais o que faltou."""
        return self.expected - self.difference

    @property
    def deviation_pct(self):
        """O que faltou em percentagem do esperado. Positivo: saiu mais do que
        os registos explicam."""
        if not self.expected:
            return None
        return (-self.difference / self.expected * 100).quantize(Decimal("0.1"), ROUND_HALF_UP)

    @property
    def value(self):
        """A diferença ao custo de referência atual do artigo."""
        custo = self.count.item.reference_cost
        if custo is None:
            return None
        return (self.difference * custo).quantize(CENT, ROUND_HALF_UP)


def _saidas(movimentos):
    """Saídas menos entradas, do ponto de vista do consumo."""
    linhas = movimentos.values("movement_type").annotate(q=Sum("quantity"))
    total = Decimal(0)
    for l in linhas:
        if l["movement_type"] in (StockMovement.Type.SAIDA, StockMovement.Type.AJUSTE_NEG):
            total += l["q"]
        else:
            total -= l["q"]
    return total


def compare(count):
    """Compara uma contagem com a anterior do mesmo artigo."""
    anterior = (
        StockCount.objects.filter(item=count.item)
        .filter(Q(counted_at__lt=count.counted_at) | Q(counted_at=count.counted_at, pk__lt=count.pk))
        .order_by("-counted_at", "-pk")
        .first()
    )
    comparacao = CountComparison(count=count, previous=anterior)
    if anterior is None:
        return comparacao
    entre = StockMovement.objects.filter(
        item=count.item, occurred_at__gt=anterior.counted_at, occurred_at__lte=count.counted_at
    ).exclude(origin=StockMovement.Origin.CONTAGEM)
    comparacao.sales = _saidas(entre.filter(origin=StockMovement.Origin.VENDA))
    comparacao.consumption = _saidas(entre.filter(origin=StockMovement.Origin.CONSUMO))
    # As quebras: as saídas registadas à mão (o docx não distingue o motivo).
    comparacao.waste = _saidas(
        entre.filter(origin=StockMovement.Origin.MANUAL, movement_type__in=[StockMovement.Type.SAIDA, StockMovement.Type.AJUSTE_NEG])
    )
    return comparacao


def comparisons(counts):
    return [compare(c) for c in counts]
