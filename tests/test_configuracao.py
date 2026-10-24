"""Configuração do restaurante: só o Admin, e arquivar em vez de apagar."""
import datetime

import pytest
from django.urls import reverse

from attendance.models import BreakType
from core.models import WorkArea
from vacations.models import BlockedPeriod, Holiday

pytestmark = pytest.mark.django_db


def test_so_o_admin_entra(client, manager, admin_user):
    client.force_login(manager)
    assert client.get(reverse("config:inicio")).status_code == 403
    client.force_login(admin_user)
    html = client.get(reverse("config:inicio")).content.decode()
    assert "Tipos de ausência" in html and "Períodos bloqueados" in html


def test_seccao_desconhecida(client, admin_user):
    client.force_login(admin_user)
    assert client.get(reverse("config:lista", args=["nada"])).status_code == 404


def test_acrescentar_e_arquivar_area(client, admin_user, restaurant):
    client.force_login(admin_user)
    client.post(reverse("config:novo", args=["areas"]), {"name": "Esplanada"})
    area = WorkArea.objects.get(restaurant=restaurant, name="Esplanada")
    client.post(reverse("config:remover", args=["areas", area.pk]))
    area.refresh_from_db()
    assert area.archived_at is not None
    client.post(reverse("config:remover", args=["areas", area.pk]))
    area.refresh_from_db()
    assert area.archived_at is None


def test_editar_tipo_de_pausa(client, admin_user, restaurant):
    tipo = BreakType.objects.get(restaurant=restaurant, name="Pausa curta")
    client.force_login(admin_user)
    client.post(reverse("config:editar", args=["pausas", tipo.pk]), {"name": "Café"})
    tipo.refresh_from_db()
    assert tipo.name == "Café" and tipo.paid is False


def test_feriado_repetido_recusado(client, admin_user, restaurant):
    client.force_login(admin_user)
    dados = {"date": "2026-06-13", "name": "Santo António"}
    client.post(reverse("config:novo", args=["feriados"]), dados)
    resp = client.post(reverse("config:novo", args=["feriados"]), dados)
    assert resp.status_code == 200
    assert Holiday.objects.filter(restaurant=restaurant).count() == 1
    assert "Santo António" in client.get(reverse("config:lista", args=["feriados"])).content.decode()


def test_feriados_nacionais_listados(client, admin_user):
    client.force_login(admin_user)
    assert "Corpo de Deus" in client.get(reverse("config:lista", args=["feriados"])).content.decode()


def test_periodo_bloqueado_com_tipos_e_apagar(client, admin_user, restaurant):
    from vacations.models import AbsenceType

    ferias = AbsenceType.objects.get(restaurant=restaurant, name="Férias")
    client.force_login(admin_user)
    client.post(
        reverse("config:novo", args=["bloqueios"]),
        {"name": "Época alta", "start": "2026-07-15", "end": "2026-08-31", "absence_types": [ferias.pk]},
    )
    periodo = BlockedPeriod.objects.get()
    assert list(periodo.absence_types.all()) == [ferias]
    assert periodo.start == datetime.date(2026, 7, 15)
    client.post(reverse("config:remover", args=["bloqueios", periodo.pk]))
    assert not BlockedPeriod.objects.exists()


def test_nao_edita_objeto_de_outro_restaurante(client, admin_user):
    from core.models import Restaurant

    outro = Restaurant.objects.create(name="Outra", slug="outra")
    area = WorkArea.objects.filter(restaurant=outro).first()
    client.force_login(admin_user)
    assert client.get(reverse("config:editar", args=["areas", area.pk])).status_code == 404
