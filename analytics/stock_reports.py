"""
Relatórios de stock e de compras (Fase 15).

Stock: o valor do stock por categoria (agora, ao custo de referência), os
artigos mais movimentados num período e o histórico de ajustes.

Compras: por fornecedor, por artigo e a evolução do preço de um artigo, pelas
receções, com o mês pela data da fatura ou da guia, como no ecrã Receções.

Os artigos são de cada casa (secção 12): entre casas, um artigo é o mesmo
quando tem o mesmo nome e a mesma unidade.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, F, Sum

from inventory.models import Item, StockMovement
from purchasing.models import ReceiptLine

ZERO = Decimal(0)
CENT = Decimal("0.01")
MAIS_MOVIMENTADOS = 20

SAIDAS = (StockMovement.Type.SAIDA, StockMovement.Type.AJUSTE_NEG)
AJUSTES = (StockMovement.Type.AJUSTE_POS, StockMovement.Type.AJUSTE_NEG)


def _euros(valor):
    return Decimal(valor or 0).quantize(CENT, ROUND_HALF_UP)


# ---- Stock -------------------------------------------------------------------


def valor_por_categoria(casas):
    """{categoria: {casa: valor}} e os totais por casa, com o stock de agora
    ao custo de referência. Um stock negativo e um artigo sem custo não
    entram; contam-se à parte."""
    valores = defaultdict(lambda: defaultdict(Decimal))
    sem_custo = defaultdict(int)
    for item in Item.objects.filter(restaurant__in=casas, is_active=True).select_related("category"):
        if item.current_stock <= 0:
            continue
        if item.reference_cost is None:
            sem_custo[item.restaurant_id] += 1
            continue
        valores[item.category.name][item.restaurant_id] += item.current_stock * item.reference_cost
    linhas = [
        {"categoria": nome, "valores": [_euros(valores[nome].get(c.pk)) for c in casas]}
        for nome in sorted(valores, key=str.casefold)
    ]
    totais = [sum((l["valores"][i] for l in linhas), ZERO) for i in range(len(casas))]
    return linhas, totais, [sem_custo.get(c.pk, 0) for c in casas]


@dataclass
class Movimentado:
    item: Item
    movimentos: int = 0
    entradas: Decimal = ZERO
    vendas: Decimal = ZERO
    consumos: Decimal = ZERO
    quebras: Decimal = ZERO
    transferencias: Decimal = ZERO
    ajustes: Decimal = ZERO  # com sinal

    @property
    def saidas(self):
        return self.vendas + self.consumos + self.quebras

    @property
    def valor_saidas(self):
        if self.item.reference_cost is None:
            return None
        return _euros(self.saidas * self.item.reference_cost)


def mais_movimentados(restaurant, inicio, fim, limite=MAIS_MOVIMENTADOS):
    """Os artigos com mais movimentos no período, com o que entrou e o que
    saiu por origem. As transferências contam com sinal: positivo é o que
    veio de outra casa."""
    movimentos = StockMovement.objects.filter(
        item__restaurant=restaurant, occurred_at__date__range=(inicio, fim)
    ).values("item", "movement_type", "origin").annotate(n=Count("pk"), q=Sum("quantity"))
    por_item = {}
    for m in movimentos:
        r = por_item.setdefault(m["item"], {"n": 0, "linhas": []})
        r["n"] += m["n"]
        r["linhas"].append(m)
    escolhidos = sorted(por_item.items(), key=lambda kv: -kv[1]["n"])[:limite]
    items = Item.objects.in_bulk([pk for pk, _ in escolhidos])
    resultado = []
    for pk, r in escolhidos:
        linha = Movimentado(item=items[pk], movimentos=r["n"])
        for m in r["linhas"]:
            q = m["q"] or ZERO
            sinal = -1 if m["movement_type"] in SAIDAS else 1
            origem = m["origin"]
            if origem == StockMovement.Origin.TRANSFERENCIA:
                linha.transferencias += sinal * q
            elif m["movement_type"] in AJUSTES:
                linha.ajustes += sinal * q
            elif origem == StockMovement.Origin.VENDA:
                linha.vendas -= sinal * q  # uma devolução por nota de crédito abate
            elif origem == StockMovement.Origin.CONSUMO:
                linha.consumos -= sinal * q
            elif m["movement_type"] == StockMovement.Type.SAIDA:
                linha.quebras += q
            else:
                linha.entradas += q
        resultado.append(linha)
    return resultado


def ajustes(restaurant, inicio, fim):
    """Os ajustes do período (contagens e ajustes à mão), do mais recente para
    o mais antigo, com o valor ao custo de referência atual."""
    lista = (
        StockMovement.objects.filter(
            item__restaurant=restaurant, occurred_at__date__range=(inicio, fim), movement_type__in=AJUSTES
        )
        .select_related("item", "created_by")
        .order_by("-occurred_at", "-pk")
    )
    linhas = []
    for m in lista:
        custo = m.item.reference_cost
        linhas.append({"mov": m, "valor": None if custo is None else _euros(m.signed_quantity * custo)})
    perdas = sum((l["valor"] for l in linhas if l["valor"] is not None and l["valor"] < 0), ZERO)
    ganhos = sum((l["valor"] for l in linhas if l["valor"] is not None and l["valor"] > 0), ZERO)
    return linhas, perdas, ganhos


# ---- Compras -----------------------------------------------------------------


def _linhas_compras(casas, inicio, fim):
    return ReceiptLine.objects.filter(
        receipt__restaurant__in=casas, receipt__document_date__range=(inicio, fim), unit_price__isnull=False
    )


def por_fornecedor(casas, inicio, fim):
    """Uma linha por fornecedor, com o total sem IVA de cada casa, o número de
    receções e o peso no total."""
    dados = (
        _linhas_compras(casas, inicio, fim)
        .values("receipt__supplier__name", "receipt__restaurant")
        .annotate(total=Sum(F("quantity") * F("unit_price")), rececoes=Count("receipt", distinct=True))
    )
    por = defaultdict(lambda: {"valores": defaultdict(Decimal), "rececoes": 0})
    for d in dados:
        f = por[d["receipt__supplier__name"]]
        f["valores"][d["receipt__restaurant"]] += Decimal(d["total"] or 0)
        f["rececoes"] += d["rececoes"]
    total = sum((sum(f["valores"].values(), ZERO) for f in por.values()), ZERO)
    linhas = []
    for nome, f in por.items():
        soma = sum(f["valores"].values(), ZERO)
        linhas.append(
            {
                "fornecedor": nome,
                "valores": [_euros(f["valores"].get(c.pk)) for c in casas],
                "total": _euros(soma),
                "rececoes": f["rececoes"],
                "peso": (soma / total * 100).quantize(Decimal("0.1"), ROUND_HALF_UP) if total else None,
            }
        )
    linhas.sort(key=lambda l: (-l["total"], l["fornecedor"].casefold()))
    totais = [sum((l["valores"][i] for l in linhas), ZERO) for i in range(len(casas))]
    return linhas, totais, _euros(total)


@dataclass
class ArtigoComprado:
    nome: str
    unidade: str
    quantidade: Decimal = ZERO
    total: Decimal = ZERO
    precos: list = field(default_factory=list)  # (data, preço, fornecedor, casa), por data

    @property
    def preco_medio(self):
        return (self.total / self.quantidade).quantize(Decimal("0.0001"), ROUND_HALF_UP) if self.quantidade else None

    @property
    def minimo(self):
        return min(p[1] for p in self.precos) if self.precos else None

    @property
    def maximo(self):
        return max(p[1] for p in self.precos) if self.precos else None

    @property
    def ultimo(self):
        return self.precos[-1][1] if self.precos else None

    @property
    def variacao(self):
        """Do primeiro ao último preço do período, em percentagem."""
        if len(self.precos) < 2 or not self.precos[0][1]:
            return None
        return ((self.precos[-1][1] - self.precos[0][1]) / self.precos[0][1] * 100).quantize(
            Decimal("0.1"), ROUND_HALF_UP
        )


def por_artigo(casas, inicio, fim):
    """Uma linha por artigo (nome e unidade, juntando as casas), do que mais
    se gastou para o que menos."""
    artigos = {}
    lista = (
        _linhas_compras(casas, inicio, fim)
        .select_related("item", "receipt__supplier", "receipt__restaurant")
        .order_by("receipt__document_date", "receipt_id", "pk")
    )
    for l in lista:
        chave = (l.item.name.casefold(), l.item.unit)
        a = artigos.get(chave)
        if a is None:
            a = artigos[chave] = ArtigoComprado(nome=l.item.name, unidade=l.item.unit)
        a.quantidade += l.quantity
        a.total += l.quantity * l.unit_price
        a.precos.append((l.receipt.document_date, l.unit_price, l.receipt.supplier.name, l.receipt.restaurant.name))
    resultado = sorted(artigos.values(), key=lambda a: (-a.total, a.nome.casefold()))
    for a in resultado:
        a.total = _euros(a.total)
    return resultado


def chave_artigo(artigo):
    return f"{artigo.nome}|{artigo.unidade}"
