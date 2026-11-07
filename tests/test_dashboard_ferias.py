"""Dashboard: os pedidos de férias por decidir aparecem em «Por tratar» e o
cartão «Em férias» mostra só quem está fora hoje (aprovado)."""
import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from vacations.models import AbsenceType, VacationRequest
from workers.models import Worker

pytestmark = pytest.mark.django_db


def _pedido(restaurant, nome, inicio, fim, status):
    w = Worker.objects.create(restaurant=restaurant, full_name=nome)
    tipo = AbsenceType.objects.get(restaurant=restaurant, name="Férias")
    return VacationRequest.objects.create(worker=w, absence_type=tipo, start_date=inicio, end_date=fim, status=status)


def test_pendente_em_por_tratar_e_cartao_so_com_quem_esta_fora(client, manager, restaurant):
    hoje = timezone.localdate()
    dia = datetime.timedelta(days=1)
    S = VacationRequest.Status
    _pedido(restaurant, "Rui Pendente", hoje + 3 * dia, hoje + 5 * dia, S.PENDENTE)
    _pedido(restaurant, "Ana Fora", hoje - dia, hoje + dia, S.APROVADO)
    _pedido(restaurant, "Joana Depois", hoje + 10 * dia, hoje + 12 * dia, S.APROVADO)

    client.force_login(manager)
    html = client.get(reverse("dashboard:home")).content.decode()

    assert '<span class="font-dados font-semibold">1</span> pedido de férias por decidir' in html
    cartao = html[html.index(">Em férias</h2>"):]
    assert "Ana Fora" in cartao
    assert "Rui Pendente" not in cartao and "Joana Depois" not in cartao


def test_sem_ninguem_fora(client, manager):
    client.force_login(manager)
    html = client.get(reverse("dashboard:home")).content.decode()
    assert "Ninguém está de férias hoje." in html
    assert "de férias por decidir" not in html
