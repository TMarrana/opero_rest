"""
Contas do ecrã Vendas (Fase 10). Tudo por dia de serviço, na casa dada, e
só com os documentos que contam (sem anulados; notas de crédito a abater).

As horas trabalhadas vêm do ponto. Num dia sem registos de ponto mas com
turnos publicados, usam-se as horas previstas, e o dia fica assinalado.
"""
import datetime
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from .models import SalesDocument, SalesLine, SalesSettings

ZERO = Decimal(0)
CENT = Decimal("0.01")
MILESIMA = Decimal("0.001")
DIAS_SEMANA = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


@dataclass
class Resumo:
    total: Decimal
    vendas: int  # documentos de venda (FT, FS, FR), sem as notas
    notas: int

    @property
    def ticket(self):
        return (self.total / self.vendas).quantize(Decimal("0.01")) if self.vendas else None


def _euros(valor):
    """As somas de decimais no SQLite vêm com casas a mais; arredonda-se ao
    cêntimo, como no ficheiro."""
    return ZERO if valor is None else Decimal(valor).quantize(CENT)


def documentos(restaurant, inicio, fim):
    return SalesDocument.objects.valid().filter(restaurant=restaurant, service_date__range=(inicio, fim))


def resumo(restaurant, inicio, fim):
    r = documentos(restaurant, inicio, fim).aggregate(
        total=Sum("net_total"),
        vendas=Count("pk", filter=Q(doc_type__in=SalesDocument.SALE_TYPES)),
        notas=Count("pk", filter=Q(doc_type=SalesDocument.Type.NC)),
    )
    return Resumo(_euros(r["total"]), r["vendas"], r["notas"])


def variacao(atual, anterior):
    """Variação em percentagem, ou None sem base de comparação."""
    if atual is None or not anterior:
        return None
    atual, anterior = Decimal(atual), Decimal(anterior)
    return ((atual - anterior) / anterior * 100).quantize(Decimal("1"))


def _dias(inicio, fim):
    dia = inicio
    while dia <= fim:
        yield dia
        dia += datetime.timedelta(days=1)


def horas_trabalhadas(restaurant, inicio, fim):
    """{dia: (horas, previstas)}. As horas do ponto, sem pausas não pagas e
    sem registos por resolver; sem ponto, as dos turnos publicados."""
    from attendance.models import TimeEntry
    from shifts.models import Shift

    reais = {}
    entradas = (
        TimeEntry.objects.filter(worker__restaurant=restaurant, work_date__range=(inicio, fim))
        .resolved()
        .prefetch_related("breaks__break_type")
    )
    for e in entradas:
        reais[e.work_date] = reais.get(e.work_date, datetime.timedelta()) + e.worked()
    previstas = {}
    for s in Shift.objects.filter(restaurant=restaurant, work_date__range=(inicio, fim), state=Shift.State.PUBLICADO):
        previstas[s.work_date] = previstas.get(s.work_date, datetime.timedelta()) + s.duration
    horas = {}
    for dia in _dias(inicio, fim):
        if reais.get(dia):
            horas[dia] = (reais[dia], False)
        elif previstas.get(dia):
            horas[dia] = (previstas[dia], True)
    return horas


def _em_horas(delta):
    return Decimal(delta.total_seconds()) / 3600


def por_dia(restaurant, inicio, fim):
    """Uma linha por dia do período, com vendas e horas, e os totais."""
    regras = SalesSettings.for_restaurant(restaurant)
    vendas = {
        r["service_date"]: r
        for r in documentos(restaurant, inicio, fim)
        .values("service_date")
        .annotate(
            total=Sum("net_total"),
            vendas=Count("pk", filter=Q(doc_type__in=SalesDocument.SALE_TYPES)),
        )
    }
    horas = horas_trabalhadas(restaurant, inicio, fim)
    linhas = []
    for dia in _dias(inicio, fim):
        v = vendas.get(dia, {})
        total = _euros(v.get("total"))
        n = v.get("vendas") or 0
        h, previstas = horas.get(dia, (None, False))
        linhas.append(_linha(dia, total, n, h, previstas, regras.hourly_cost))
    total = sum((l["total"] for l in linhas), ZERO)
    h_total = sum((l["horas"] for l in linhas if l["horas"]), datetime.timedelta())
    totais = _linha(None, total, sum(l["vendas"] for l in linhas), h_total or None, False, regras.hourly_cost)
    maximo = max((l["total"] for l in linhas), default=ZERO)
    for l in linhas:
        l["barra"] = int(l["total"] / maximo * 100) if maximo > 0 and l["total"] > 0 else 0
    return linhas, totais


def _linha(dia, total, vendas, horas, previstas, custo_hora):
    por_hora = custo = None
    if horas and horas.total_seconds() > 0:
        h = _em_horas(horas)
        por_hora = (total / h).quantize(Decimal("0.01"))
        if custo_hora and total > 0:
            custo = (custo_hora * h / total * 100).quantize(Decimal("0.1"))
    return {
        "dia": dia,
        "fim_de_semana": dia is not None and dia.weekday() >= 5,
        "total": total,
        "vendas": vendas,
        "ticket": (total / vendas).quantize(Decimal("0.01")) if vendas else None,
        "horas": horas,
        "previstas": previstas,
        "por_hora": por_hora,
        "custo_pessoal": custo,
    }


def mapa_semana(restaurant, inicio, fim):
    """Vendas por dia da semana e hora, nas horas de serviço. As horas
    começam na hora de corte, para a noite ficar seguida."""
    corte = SalesSettings.for_restaurant(restaurant).day_cutoff_hour
    grelha = [[ZERO] * 24 for _ in range(7)]
    usadas = set()
    for dia, hora, total in documentos(restaurant, inicio, fim).values_list("service_date", "system_entry", "net_total"):
        h = timezone.localtime(hora).hour
        grelha[dia.weekday()][h] += total
        usadas.add(h)
    if not usadas:
        return None
    ordem = [(corte + i) % 24 for i in range(24)]
    posicoes = [i for i, h in enumerate(ordem) if h in usadas]
    horas = ordem[posicoes[0] : posicoes[-1] + 1]
    maximo = max(max(linha) for linha in grelha)
    if maximo <= 0:
        maximo = Decimal(1)
    linhas = []
    for wd in range(7):
        celulas = []
        for h in horas:
            v = grelha[wd][h]
            celulas.append({"hora": h, "valor": v, "nivel": round(float(v / maximo), 2) if v > 0 else 0})
        linhas.append({"dia": DIAS_SEMANA[wd], "celulas": celulas, "total": sum(grelha[wd], ZERO)})
    return {"horas": horas, "linhas": linhas}


def _linhas(restaurant, inicio, fim):
    return SalesLine.objects.filter(document__in=documentos(restaurant, inicio, fim))


def _arredondar(linhas):
    for l in linhas:
        q = Decimal(l["quantidade"] or 0).quantize(MILESIMA)
        l["quantidade"] = q.quantize(Decimal(1)) if q == q.to_integral_value() else q.normalize()
        l["total"] = _euros(l["total"])
    return linhas


def por_produto(restaurant, inicio, fim):
    return _arredondar(
        list(
            _linhas(restaurant, inicio, fim)
            .values("product__code", "product__description", "product__group")
            .annotate(quantidade=Sum("quantity"), total=Sum("net_amount"))
            .order_by("-total", "product__description")
        )
    )


def por_familia(restaurant, inicio, fim):
    linhas = _arredondar(
        list(
            _linhas(restaurant, inicio, fim)
            .values("product__group")
            .annotate(quantidade=Sum("quantity"), total=Sum("net_amount"))
            .order_by("-total")
        )
    )
    soma = sum((l["total"] for l in linhas), ZERO)
    for l in linhas:
        l["peso"] = (l["total"] / soma * 100).quantize(Decimal("0.1")) if soma > 0 else None
    return linhas


def ultimo_dia(restaurant):
    """O último dia de serviço com vendas importadas, ou None."""
    return (
        SalesDocument.objects.valid()
        .filter(restaurant=restaurant)
        .order_by("-service_date")
        .values_list("service_date", flat=True)
        .first()
    )
