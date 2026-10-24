"""Fase 6: planeador de turnos."""
import datetime

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from attendance.services import close_shift, open_shift
from core.models import WorkArea
from shifts import services
from shifts.models import RestDay, Shift, ShiftTemplate, WeekPublication
from vacations.models import AbsenceType
from vacations.services import cancel_request, count_days, create_request
from workers.models import Worker

pytestmark = pytest.mark.django_db

T = datetime.time
DIA = datetime.timedelta(days=1)


@pytest.fixture
def worker(restaurant, staff_user):
    staff_user.set_staff_pin("2468")
    return Worker.objects.create(restaurant=restaurant, full_name="Marta Silva", user=staff_user)


@pytest.fixture
def outro(restaurant):
    return Worker.objects.create(restaurant=restaurant, full_name="Rui Costa")


@pytest.fixture
def almoco(restaurant):
    sala = WorkArea.objects.get(restaurant=restaurant, name="Sala")
    return ShiftTemplate.objects.create(restaurant=restaurant, name="Almoço", start=T(11), end=T(16), work_area=sala)


@pytest.fixture
def jantar(restaurant):
    return ShiftTemplate.objects.create(restaurant=restaurant, name="Jantar", start=T(19), end=T(23, 30))


@pytest.fixture
def fecho(restaurant):
    return ShiftTemplate.objects.create(restaurant=restaurant, name="Fecho", start=T(20), end=T(2))


@pytest.fixture
def proxima():
    """Segunda-feira da próxima semana."""
    return services.week_start(timezone.localdate()) + 7 * DIA


def _ferias(restaurant):
    return AbsenceType.objects.get(restaurant=restaurant, name="Férias")


class TestCriar:
    def test_turno_a_partir_de_guardado(self, restaurant, worker, almoco, proxima):
        s = services.create_shift(restaurant=restaurant, worker=worker, day=proxima, template=almoco)
        assert s.state == Shift.State.RASCUNHO
        assert timezone.localtime(s.start_at).time() == T(11)
        assert s.work_area.name == "Sala"

    def test_turno_da_noite_conta_no_dia_em_que_comeca(self, restaurant, worker, fecho, proxima):
        s = services.create_shift(restaurant=restaurant, worker=worker, day=proxima, template=fecho)
        assert s.work_date == proxima
        assert timezone.localtime(s.end_at).date() == proxima + DIA
        assert s.duration == datetime.timedelta(hours=6)

    def test_horas_a_mao(self, restaurant, worker, proxima):
        s = services.create_shift(restaurant=restaurant, worker=worker, day=proxima, start=T(9), end=T(13))
        assert s.duration == datetime.timedelta(hours=4)

    def test_lote_nao_duplica(self, restaurant, worker, outro, almoco, proxima):
        dias = [proxima, proxima + DIA]
        assert services.bulk_create(restaurant=restaurant, template=almoco, workers=[worker, outro], days=dias) == 4
        assert services.bulk_create(restaurant=restaurant, template=almoco, workers=[worker, outro], days=dias) == 0

    def test_copiar_semana_em_rascunho(self, restaurant, worker, almoco, proxima, manager):
        services.create_shift(restaurant=restaurant, worker=worker, day=proxima, template=almoco)
        services.set_rest_day(restaurant=restaurant, worker=worker, day=proxima + DIA)
        services.publish_week(restaurant=restaurant, week=proxima, user=manager)
        turnos, folgas = services.copy_week(restaurant=restaurant, source=proxima, target=proxima + 7 * DIA)
        assert (turnos, folgas) == (1, 1)
        copia = Shift.objects.get(work_date=proxima + 7 * DIA)
        assert copia.state == Shift.State.RASCUNHO
        assert RestDay.objects.get(date=proxima + 8 * DIA).state == RestDay.State.RASCUNHO


class TestConflitos:
    def test_sobreposicao(self, restaurant, worker, almoco, proxima):
        services.create_shift(restaurant=restaurant, worker=worker, day=proxima, template=almoco)
        s = services.create_shift(restaurant=restaurant, worker=worker, day=proxima, start=T(15), end=T(18))
        assert "Sobrepõe" in services.conflicts(restaurant, proxima)[s.pk][0]

    def test_descanso_minimo(self, restaurant, worker, fecho, proxima):
        services.create_shift(restaurant=restaurant, worker=worker, day=proxima, template=fecho)  # até às 2h
        s = services.create_shift(restaurant=restaurant, worker=worker, day=proxima + DIA, start=T(9), end=T(15))
        assert "descanso" in services.conflicts(restaurant, proxima)[s.pk][0]

    def test_folga_e_ausencia_aprovada(self, restaurant, worker, almoco, proxima, manager):
        s1 = services.create_shift(restaurant=restaurant, worker=worker, day=proxima, template=almoco)
        services.set_rest_day(restaurant=restaurant, worker=worker, day=proxima)
        create_request(
            worker=worker, absence_type=_ferias(restaurant), start_date=proxima + 2 * DIA,
            end_date=proxima + 2 * DIA, created_by=manager,
        )
        s2 = services.create_shift(restaurant=restaurant, worker=worker, day=proxima + 2 * DIA, template=almoco)
        c = services.conflicts(restaurant, proxima)
        assert c[s1.pk] == ["Dia de folga"]
        assert c[s2.pk] == ["Férias aprovada"]

    def test_ausencia_pendente_nao_e_conflito(self, restaurant, worker, almoco, proxima):
        create_request(worker=worker, absence_type=_ferias(restaurant), start_date=proxima, end_date=proxima)
        services.create_shift(restaurant=restaurant, worker=worker, day=proxima, template=almoco)
        assert services.conflicts(restaurant, proxima) == {}

    def test_conflicts_block_publish(self, restaurant, worker, almoco, proxima, manager):
        services.create_shift(restaurant=restaurant, worker=worker, day=proxima, template=almoco)
        services.create_shift(restaurant=restaurant, worker=worker, day=proxima, start=T(12), end=T(14))
        with pytest.raises(ValidationError, match="2 turno"):
            services.publish_week(restaurant=restaurant, week=proxima, user=manager)
        assert not Shift.objects.filter(state=Shift.State.PUBLICADO).exists()


class TestPublicacao:
    def test_publicar_e_resumo(self, restaurant, worker, almoco, proxima, manager):
        services.create_shift(restaurant=restaurant, worker=worker, day=proxima, template=almoco)
        mud = services.changes(restaurant, proxima)
        assert len(mud["novos"]) == 1 and mud["afetados"] == ["Marta Silva"]
        pub = services.publish_week(restaurant=restaurant, week=proxima, user=manager)
        assert "1 novo" in pub.summary and "Marta Silva" in pub.summary
        assert Shift.objects.get().state == Shift.State.PUBLICADO

    def test_editar_ou_apagar_publicado_exige_nova_publicacao(self, restaurant, worker, almoco, jantar, proxima, manager):
        a = services.create_shift(restaurant=restaurant, worker=worker, day=proxima, template=almoco)
        b = services.create_shift(restaurant=restaurant, worker=worker, day=proxima + DIA, template=jantar)
        services.publish_week(restaurant=restaurant, week=proxima, user=manager)
        a.refresh_from_db()
        services.update_shift(shift=a, start=T(12), end=T(16))
        b.refresh_from_db()
        services.remove_shift(shift=b)
        mud = services.changes(restaurant, proxima)
        assert len(mud["alterados"]) == 1 and len(mud["removidos"]) == 1
        services.publish_week(restaurant=restaurant, week=proxima, user=manager)
        assert list(Shift.objects.values_list("state", flat=True)) == [Shift.State.PUBLICADO]

    def test_despublicar(self, restaurant, worker, almoco, proxima, manager):
        s = services.create_shift(restaurant=restaurant, worker=worker, day=proxima, template=almoco)
        services.publish_week(restaurant=restaurant, week=proxima, user=manager)
        s.refresh_from_db()
        services.unpublish_shift(shift=s)
        assert s.state == Shift.State.RASCUNHO

    def test_staff_never_sees_draft_shift(self, client, restaurant, worker, outro, almoco, jantar, staff_user, manager):
        """Invariante 10: rascunho e reserva nunca aparecem ao colaborador."""
        hoje = timezone.localdate()
        services.create_shift(restaurant=restaurant, worker=worker, day=hoje + DIA, template=almoco)
        client.force_login(staff_user)
        assert "11:00" not in client.get(reverse("staff:turnos")).content.decode()

        services.publish_week(restaurant=restaurant, week=hoje + DIA, user=manager)
        html = client.get(reverse("staff:turnos")).content.decode()
        assert "11:00" in html and "Almoço" in html

        reserva = services.create_shift(restaurant=restaurant, worker=worker, day=hoje + 2 * DIA, template=jantar)
        reserva.state = Shift.State.RESERVA
        reserva.save()
        assert "19:00" not in client.get(reverse("staff:turnos")).content.decode()


class TestAusencias:
    def test_approved_absence_moves_shift_to_backup(self, restaurant, worker, almoco, proxima, manager):
        s = services.create_shift(restaurant=restaurant, worker=worker, day=proxima, template=almoco)
        services.publish_week(restaurant=restaurant, week=proxima, user=manager)
        pedido = create_request(worker=worker, absence_type=_ferias(restaurant), start_date=proxima, end_date=proxima)
        from vacations.services import decide_request

        decide_request(request_obj=pedido, user=manager, approve=True)
        s.refresh_from_db()
        assert s.state == Shift.State.RESERVA

        cancel_request(request_obj=pedido, worker=worker)
        s.refresh_from_db()
        assert s.state == Shift.State.RASCUNHO

    def test_meio_dia_nao_passa_a_reserva(self, restaurant, worker, almoco, proxima, manager):
        s = services.create_shift(restaurant=restaurant, worker=worker, day=proxima, template=almoco)
        create_request(
            worker=worker, absence_type=_ferias(restaurant), start_date=proxima, end_date=proxima,
            half_day=True, created_by=manager,
        )
        s.refresh_from_db()
        assert s.state == Shift.State.RASCUNHO

    def test_rest_day_not_deducted(self, restaurant, worker, proxima):
        """Uma folga não desconta dias de férias (R-037)."""
        assert count_days(worker, proxima, proxima + 4 * DIA) == 5 - _feriados_uteis(proxima)
        services.set_rest_day(restaurant=restaurant, worker=worker, day=proxima + DIA)
        assert count_days(worker, proxima, proxima + 4 * DIA) == 4 - _feriados_uteis(proxima)

    def test_semana_planeada_so_conta_dias_com_turno(self, restaurant, worker, almoco, proxima, manager):
        # Turnos de sábado e domingo: são esses os dias de trabalho.
        for d in (proxima + 5 * DIA, proxima + 6 * DIA):
            services.create_shift(restaurant=restaurant, worker=worker, day=d, template=almoco)
        services.publish_week(restaurant=restaurant, week=proxima, user=manager)
        assert count_days(worker, proxima, proxima + 6 * DIA) == 2 - sum(
            1 for d in (proxima + 5 * DIA, proxima + 6 * DIA) if d in _feriados(proxima)
        )


def _feriados(semana):
    from vacations.holidays import national_holidays

    return {d for ano in {semana.year, (semana + 6 * DIA).year} for d in national_holidays(ano)}


def _feriados_uteis(semana):
    return sum(1 for i in range(5) if semana + i * DIA in _feriados(semana))


class TestPlaneadoRealizado:
    def test_limite_por_resolver_vem_do_turno(self, restaurant, worker, manager):
        ontem = timezone.localdate() - DIA
        services.create_shift(restaurant=restaurant, worker=worker, day=ontem, start=T(8), end=T(12))
        services.publish_week(restaurant=restaurant, week=ontem, user=manager)
        entry = open_shift(worker=worker, at=timezone.make_aware(datetime.datetime.combine(ontem, T(8))))
        # Com turno até às 12h, a entrada fica por resolver às 16h de ontem,
        # muito antes das 14 horas do limite fixo.
        assert entry.deadline() == timezone.make_aware(datetime.datetime.combine(ontem, T(16)))
        assert entry.is_unresolved()

    def test_vista_da_equipa_assinala_atraso(self, client, restaurant, worker, manager):
        ontem = timezone.localdate() - DIA
        services.create_shift(restaurant=restaurant, worker=worker, day=ontem, start=T(9), end=T(17))
        services.publish_week(restaurant=restaurant, week=ontem, user=manager)
        open_shift(worker=worker, at=timezone.make_aware(datetime.datetime.combine(ontem, T(9, 25))))
        close_shift(worker=worker, at=timezone.make_aware(datetime.datetime.combine(ontem, T(16))))
        client.force_login(manager)
        html = client.get(reverse("attendance:dia") + f"?dia={ontem.isoformat()}").content.decode()
        assert "Entrou 25 min depois" in html and "Saiu 60 min antes" in html

    def test_sem_marcacao(self, client, restaurant, worker, manager):
        ontem = timezone.localdate() - DIA
        services.create_shift(restaurant=restaurant, worker=worker, day=ontem, start=T(9), end=T(17))
        services.publish_week(restaurant=restaurant, week=ontem, user=manager)
        client.force_login(manager)
        assert "Sem marcação" in client.get(reverse("attendance:dia") + f"?dia={ontem.isoformat()}").content.decode()


class TestVistas:
    def test_planeador_e_painel(self, client, restaurant, worker, almoco, proxima, manager):
        client.force_login(manager)
        html = client.get(reverse("shifts:planeador") + f"?semana={proxima.isoformat()}").content.decode()
        assert "Marta Silva" in html and "Copiar semana anterior" in html
        painel = client.get(reverse("shifts:celula", args=[worker.pk, proxima.isoformat()])).content.decode()
        assert "Acrescentar turno" in painel
        client.post(
            reverse("shifts:celula", args=[worker.pk, proxima.isoformat()]),
            {"acao": "turno", "template": almoco.pk},
        )
        assert Shift.objects.filter(worker=worker, work_date=proxima).exists()
        client.post(reverse("shifts:celula", args=[worker.pk, (proxima + DIA).isoformat()]), {"acao": "folga"})
        assert RestDay.objects.filter(worker=worker, date=proxima + DIA).exists()

    def test_colaborador_nao_entra_no_planeador(self, client, staff_user):
        client.force_login(staff_user)
        assert client.get(reverse("shifts:planeador")).status_code == 403

    def test_turnos_guardados_na_configuracao(self, client, restaurant, manager):
        client.force_login(manager)
        client.post(reverse("config:novo", args=["turnos"]), {"name": "Dobra", "start": "11:00", "end": "23:00"})
        assert ShiftTemplate.objects.filter(restaurant=restaurant, name="Dobra").exists()


def test_aceitacao_fase_6(client, restaurant, worker, outro, almoco, jantar, staff_user, manager):
    """Aceitação: o gerente copia a semana anterior, ajusta dois turnos a
    partir dos guardados, marca uma folga e vê um conflito com férias
    aprovadas. Depois de o resolver publica, e o colaborador vê os seus
    turnos no telemóvel."""
    hoje = timezone.localdate()
    esta = services.week_start(hoje)
    seguinte = esta + 7 * DIA
    for i in range(5):
        services.create_shift(restaurant=restaurant, worker=worker, day=esta + i * DIA, template=almoco)
    services.publish_week(restaurant=restaurant, week=esta, user=manager)

    client.force_login(manager)
    client.post(reverse("shifts:copiar"), {"semana": seguinte.isoformat()})
    assert Shift.objects.filter(work_date__range=(seguinte, seguinte + 6 * DIA)).count() == 5

    # Ajustar dois turnos: terça e quarta passam a jantar.
    for d in (seguinte + DIA, seguinte + 2 * DIA):
        s = Shift.objects.get(worker=worker, work_date=d)
        client.post(reverse("shifts:celula", args=[worker.pk, d.isoformat()]), {"acao": "apagar", "turno": s.pk})
        client.post(reverse("shifts:celula", args=[worker.pk, d.isoformat()]), {"acao": "turno", "template": jantar.pk})
    client.post(reverse("shifts:celula", args=[outro.pk, seguinte.isoformat()]), {"acao": "folga"})

    create_request(
        worker=worker, absence_type=_ferias(restaurant), start_date=seguinte + 3 * DIA,
        end_date=seguinte + 3 * DIA, created_by=manager,
    )
    # A ausência aprovada passa o turno de quinta a reserva; um turno novo
    # nesse dia é um conflito.
    client.post(
        reverse("shifts:celula", args=[worker.pk, (seguinte + 3 * DIA).isoformat()]), {"acao": "turno", "template": jantar.pk}
    )
    html = client.get(reverse("shifts:publicar") + f"?semana={seguinte.isoformat()}").content.decode()
    assert "Férias aprovada" in html
    client.post(reverse("shifts:publicar"), {"semana": seguinte.isoformat()})
    assert not WeekPublication.objects.filter(week=seguinte).exists()

    conflito = Shift.objects.get(worker=worker, work_date=seguinte + 3 * DIA, state=Shift.State.RASCUNHO)
    client.post(
        reverse("shifts:celula", args=[worker.pk, conflito.work_date.isoformat()]), {"acao": "apagar", "turno": conflito.pk}
    )
    client.post(reverse("shifts:publicar"), {"semana": seguinte.isoformat()})
    assert WeekPublication.objects.filter(week=seguinte).exists()

    # A terça da semana seguinte está sempre dentro dos 14 dias da vista.
    client.force_login(staff_user)
    assert "Jantar" in client.get(reverse("staff:turnos")).content.decode()
