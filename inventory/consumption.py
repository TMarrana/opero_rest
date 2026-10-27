"""
Consumos internos (Fase 12): refeições do pessoal, ofertas, provas e o que
o dono leva. Cada linha é uma SAIDA de origem consumo interno, pelo
`register_movement()` (invariante 1), valorizada ao custo de referência do
momento. O valor fica guardado e não se recalcula quando o custo muda.

Um consumo não se apaga (invariante 2): anula-se, com uma ENTRADA da mesma
origem que repõe o stock, e deixa de contar no mapa do mês.
"""
import csv
import io
from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from attendance.month import month_range

from .models import ConsumptionLine, ConsumptionSettings, InternalConsumption, StockMovement
from .services import register_movement

CENT = Decimal("0.01")


def meals_check(*, worker, day, extra=0, restaurant=None):
    """(refeições no dia, limite) para um trabalhador, contando `extra`
    refeições ainda por registar. O limite é o da casa onde comeu (por
    omissão, a principal) por turno, vezes os turnos do dia em qualquer
    casa do grupo: os registos de ponto, ou, sem ponto, os turnos
    publicados. Sem limite configurado, devolve None no limite."""
    from attendance.models import TimeEntry
    from shifts.models import Shift

    por_turno = ConsumptionSettings.for_restaurant(restaurant or worker.restaurant).meals_per_shift
    refeicoes = (
        InternalConsumption.objects.filter(
            worker=worker, consumed_on=day, reason=InternalConsumption.Reason.REFEICAO, cancelled_at__isnull=True
        ).count()
        + extra
    )
    if por_turno is None:
        return refeicoes, None
    turnos = TimeEntry.objects.filter(worker=worker, work_date=day).count() or Shift.objects.filter(
        worker=worker, work_date=day, state=Shift.State.PUBLICADO
    ).count()
    return refeicoes, por_turno * turnos


def register_consumption(*, restaurant, worker, reason, day, lines, user, note=""):
    """Regista um consumo. `lines` é uma lista de (artigo, quantidade); as
    quantidades vazias ficam de fora. Tudo numa transação. Devolve o
    consumo; `over_limit` diz se passou o limite de refeições (não bloqueia)."""
    if reason not in InternalConsumption.Reason.values:
        raise ValidationError("Escolha o motivo do consumo.")
    if worker is not None and not worker.works_in(restaurant):
        raise ValidationError(f"{worker} não trabalha nesta casa.")
    if reason == InternalConsumption.Reason.REFEICAO and worker is None:
        raise ValidationError("Uma refeição do pessoal é de um trabalhador. Escolha quem comeu.")
    if day is None:
        raise ValidationError("Indique o dia do consumo.")
    if day > timezone.localdate():
        raise ValidationError("O dia do consumo não pode ser no futuro.")
    validas, vistos = [], set()
    for item, quantidade in lines:
        if item.restaurant_id != restaurant.pk:
            raise ValidationError(f"{item} não é um artigo desta casa.")
        if not quantidade:
            continue
        if item.pk in vistos:
            raise ValidationError(f"{item} aparece duas vezes. Junte as quantidades numa só linha.")
        vistos.add(item.pk)
        validas.append((item, Decimal(quantidade)))
    if not validas:
        raise ValidationError("Indique pelo menos um artigo e a quantidade.")

    acima = False
    if reason == InternalConsumption.Reason.REFEICAO:
        refeicoes, limite = meals_check(worker=worker, day=day, extra=1, restaurant=restaurant)
        acima = limite is not None and refeicoes > limite

    with transaction.atomic():
        consumo = InternalConsumption.objects.create(
            restaurant=restaurant, worker=worker, reason=reason, consumed_on=day, note=note, created_by=user, over_limit=acima
        )
        quem = worker.full_name if worker else "a casa"
        for item, quantidade in validas:
            movimento = register_movement(
                item=item,
                movement_type=StockMovement.Type.SAIDA,
                quantity=quantidade,
                user=user,
                reason=f"Consumo interno de {quem} · {consumo.get_reason_display().lower()}",
                reference=consumo.reference,
                origin=StockMovement.Origin.CONSUMO,
            )
            # O custo lê-se depois do lock do movimento, o do momento.
            custo = item.__class__.objects.values_list("reference_cost", flat=True).get(pk=item.pk)
            ConsumptionLine.objects.create(
                consumption=consumo,
                item=item,
                quantity=quantidade,
                unit_cost=custo,
                value=None if custo is None else (custo * quantidade).quantize(CENT),
                movement=movimento,
            )
    return consumo


def cancel_consumption(*, consumption, user, reason):
    """Anula um consumo registado por engano: uma ENTRADA por linha repõe o
    stock, e o consumo deixa de contar. Nada se apaga."""
    if not (reason or "").strip():
        raise ValidationError("Diga porque anula o consumo: o motivo fica registado.")
    with transaction.atomic():
        consumo = InternalConsumption.objects.select_for_update().get(pk=consumption.pk)
        if consumo.cancelled_at is not None:
            raise ValidationError(f"O consumo {consumo.reference} já estava anulado.")
        for linha in consumo.lines.select_related("item"):
            linha.reversal = register_movement(
                item=linha.item,
                movement_type=StockMovement.Type.ENTRADA,
                quantity=linha.quantity,
                user=user,
                reason=f"Anulação do consumo {consumo.reference}: {reason.strip()}"[:200],
                reference=consumo.reference,
                origin=StockMovement.Origin.CONSUMO,
            )
            linha.save(update_fields=["reversal"])
        consumo.cancelled_at, consumo.cancelled_by, consumo.cancel_reason = timezone.now(), user, reason.strip()[:200]
        consumo.save(update_fields=["cancelled_at", "cancelled_by", "cancel_reason", "updated_at"])
    return consumo


def month_lines(restaurant, month):
    inicio, fim = month_range(month)
    return (
        ConsumptionLine.objects.filter(
            consumption__restaurant=restaurant,
            consumption__consumed_on__range=(inicio, fim),
            consumption__cancelled_at__isnull=True,
        )
        .select_related("consumption__worker", "item")
        .order_by("consumption__worker__full_name", "consumption__consumed_on", "consumption_id", "item__name")
    )


def month_map(restaurant, month):
    """Uma linha por pessoa (e uma para a casa): refeições, outros consumos,
    valor e linhas sem custo."""
    pessoas = defaultdict(lambda: {"refeicoes": set(), "outros": set(), "valor": Decimal(0), "sem_custo": 0, "acima": set()})
    for l in month_lines(restaurant, month):
        c = l.consumption
        p = pessoas[c.worker]
        (p["refeicoes"] if c.reason == InternalConsumption.Reason.REFEICAO else p["outros"]).add(c.pk)
        if c.over_limit:
            p["acima"].add(c.pk)
        if l.value is None:
            p["sem_custo"] += 1
        else:
            p["valor"] += l.value
    linhas = [
        {
            "worker": w,
            "quem": w.full_name if w else "A casa",
            "refeicoes": len(p["refeicoes"]),
            "outros": len(p["outros"]),
            "acima": len(p["acima"]),
            "valor": p["valor"],
            "sem_custo": p["sem_custo"],
        }
        for w, p in pessoas.items()
    ]
    # Os trabalhadores por nome, e a casa no fim.
    return sorted(linhas, key=lambda l: (l["worker"] is None, l["quem"]))


def _num(valor):
    if valor is None:
        return ""
    valor = Decimal(valor)
    texto = str(valor.quantize(Decimal(1))) if valor == valor.to_integral_value() else format(valor.normalize(), "f")
    return texto.replace(".", ",")


def export_csv(restaurant, month):
    """O mapa do mês para o contabilista: uma linha por artigo consumido e,
    no fim, o total de cada pessoa. Separador ';', BOM e vírgula decimal,
    como a exportação do ponto."""
    saida = io.StringIO()
    escrita = csv.writer(saida, delimiter=";")
    escrita.writerow(["Pessoa", "Dia", "Motivo", "Artigo", "Quantidade", "Unidade", "Custo unitário", "Valor", "Acima do limite", "Consumo"])
    for l in month_lines(restaurant, month):
        c = l.consumption
        escrita.writerow(
            [c.who, c.consumed_on.isoformat(), c.get_reason_display(), l.item.name, _num(l.quantity), l.item.unit,
             _num(l.unit_cost), _num(l.value), "sim" if c.over_limit else "", c.reference]
        )
    escrita.writerow([])
    escrita.writerow(["Totais do mês", "Refeições", "Outros consumos", "Valor", "Linhas sem custo"])
    for p in month_map(restaurant, month):
        escrita.writerow([p["quem"], p["refeicoes"], p["outros"], _num(p["valor"]), p["sem_custo"] or ""])
    return "﻿" + saida.getvalue()
