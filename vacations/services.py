"""Decisões de férias — sempre com autor, data e observação (invariante 5)."""
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import VacationRequest


def decide_request(*, request_obj, user, approve, note=""):
    if request_obj.status != VacationRequest.Status.PENDENTE:
        raise ValidationError("Este pedido já foi decidido.")
    request_obj.status = (
        VacationRequest.Status.APROVADO if approve else VacationRequest.Status.RECUSADO
    )
    request_obj.decided_by = user
    request_obj.decided_at = timezone.now()
    request_obj.decision_note = note.strip()
    request_obj.save()
    return request_obj
