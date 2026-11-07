"""
Apagar um trabalhador (decidido a 2026-11-04). Só se apaga uma ficha sem
histórico: registos de ponto, fechos do mês, pedidos de férias ou
consumos têm de ficar guardados, por isso uma ficha com eles desativa-se.
Os turnos planeados, as folgas e os saldos de férias apagam-se com a ficha.
A conta da app, se houver, apaga-se também; se a conta tiver registado
alguma coisa (é autora de movimentos, por exemplo), fica desativada.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import ProtectedError


def delete_blockers(worker):
    """O histórico que impede apagar a ficha, em texto: lista vazia se se
    pode apagar."""
    from attendance.models import TimeEntry

    contagens = [
        # Também os apagados: ficam guardados (invariante 7).
        (TimeEntry.all_objects.filter(worker=worker).count(), "registo de ponto", "registos de ponto"),
        (worker.correction_requests.count(), "pedido de correção", "pedidos de correção"),
        (worker.month_closes.count(), "fecho do mês", "fechos do mês"),
        (worker.vacation_requests.count(), "pedido de férias ou ausência", "pedidos de férias ou ausências"),
        (worker.consumptions.count(), "consumo", "consumos"),
    ]
    return [f"{n} {um if n == 1 else varios}" for n, um, varios in contagens if n]


def delete_worker(*, worker, user):
    """Apaga a ficha e a conta da app. Recusa se houver histórico, ou se a
    conta for de quem está a apagar."""
    bloqueios = delete_blockers(worker)
    if bloqueios:
        raise ValidationError(
            f"{worker.full_name} tem histórico ({', '.join(bloqueios)}), que tem de ficar guardado. "
            "Desative a ficha em vez de a eliminar."
        )
    conta = worker.user
    if conta is not None and conta.pk == user.pk:
        raise ValidationError("Não pode eliminar a sua própria ficha.")
    with transaction.atomic():
        worker.delete()
        if conta is not None:
            try:
                with transaction.atomic():
                    conta.delete()
            except ProtectedError:
                conta.is_active = False
                conta.save(update_fields=["is_active"])
