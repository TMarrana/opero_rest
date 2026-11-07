"""Consultas de leitura do ponto: perguntas do tipo «quem?» que várias
páginas têm de responder da mesma maneira."""
from django.db.models import Q

from .month import month_range


def workers_for_month(qs, month):
    """Os trabalhadores que pertencem ao fecho de um mês (qualquer dia do mês).

    Entra quem já tinha começado até ao fim do mês e: está ativo sem data de
    saída, ou saiu no mês ou depois, ou tem registos de ponto (não anulados)
    nesse mês. Assim quem saiu a meio do mês continua no fecho e no CSV, e
    quem só começa no mês seguinte não aparece como por aprovar."""
    inicio, fim = month_range(month)
    ja_comecou = Q(start_date__isnull=True) | Q(start_date__lte=fim)
    nesse_mes = (
        Q(is_active=True, end_date__isnull=True)
        | Q(end_date__gte=inicio)
        | Q(
            time_entries__work_date__range=(inicio, fim),
            time_entries__annulled_at__isnull=True,
        )
    )
    return qs.filter(ja_comecou).filter(nesse_mes).distinct().order_by("full_name")
