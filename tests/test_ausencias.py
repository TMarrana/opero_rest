"""Fase 5: tipos de ausência, meio dia, cancelamento, saldo, feriados e
períodos bloqueados."""
import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from vacations.holidays import easter, national_holidays
from vacations.models import AbsenceType, Allowance, BlockedPeriod, Holiday, VacationRequest
from vacations.services import (
    balance,
    cancel_request,
    count_days,
    create_request,
    decide_request,
)
from workers.models import Worker

pytestmark = pytest.mark.django_db

D = datetime.date


@pytest.fixture
def worker(restaurant, staff_user):
    staff_user.set_staff_pin("2468")
    return Worker.objects.create(restaurant=restaurant, full_name="Marta Silva", user=staff_user)


@pytest.fixture
def ferias(restaurant):
    return AbsenceType.objects.get(restaurant=restaurant, name="Férias")


@pytest.fixture
def baixa(restaurant):
    return AbsenceType.objects.get(restaurant=restaurant, name="Baixa médica")


def _futuro(dias):
    return timezone.localdate() + datetime.timedelta(days=dias)


class TestFeriados:
    def test_pascoa(self):
        assert easter(2026) == D(2026, 4, 5)
        assert easter(2027) == D(2027, 3, 28)

    def test_feriados_moveis_2026(self):
        f = national_holidays(2026)
        assert f[D(2026, 4, 3)] == "Sexta-feira Santa"
        assert f[D(2026, 6, 4)] == "Corpo de Deus"
        assert len(f) == 13

    def test_days_taken_skips_holidays(self, worker, restaurant):
        """O cálculo não conta fins de semana nem feriados, nacionais ou do
        restaurante."""
        # 8 a 12 de junho de 2026: segunda a sexta, com o 10 de junho.
        assert count_days(worker, D(2026, 6, 8), D(2026, 6, 12)) == 4
        Holiday.objects.create(restaurant=restaurant, date=D(2026, 6, 12), name="Feriado municipal")
        assert count_days(worker, D(2026, 6, 8), D(2026, 6, 12)) == 3

    def test_meio_dia(self, worker):
        assert count_days(worker, D(2026, 6, 8), D(2026, 6, 8), half_day=True) == Decimal("0.5")


class TestTipos:
    def test_tipos_de_origem(self, restaurant):
        nomes = set(AbsenceType.objects.filter(restaurant=restaurant).values_list("name", flat=True))
        assert {"Férias", "Falta justificada", "Baixa médica", "Licença parental", "Formação"} == nomes

    def test_tipo_sem_aprovacao_fica_aprovado(self, worker, baixa):
        pedido = create_request(worker=worker, absence_type=baixa, start_date=_futuro(3), end_date=_futuro(5))
        assert pedido.status == VacationRequest.Status.APROVADO
        assert pedido.decided_by is None

    def test_manager_created_absence_is_approved(self, worker, ferias, manager):
        pedido = create_request(
            worker=worker, absence_type=ferias, start_date=_futuro(10), end_date=_futuro(12), created_by=manager
        )
        assert pedido.status == VacationRequest.Status.APROVADO
        assert pedido.decided_by == manager

    def test_ferias_ficam_pendentes(self, worker, ferias):
        pedido = create_request(worker=worker, absence_type=ferias, start_date=_futuro(10), end_date=_futuro(12))
        assert pedido.status == VacationRequest.Status.PENDENTE

    def test_meio_dia_so_num_dia_e_em_tipo_que_permite(self, worker, ferias, baixa):
        with pytest.raises(ValidationError, match="Meio dia"):
            create_request(worker=worker, absence_type=ferias, start_date=_futuro(10), end_date=_futuro(11), half_day=True)
        with pytest.raises(ValidationError, match="Meio dia"):
            create_request(worker=worker, absence_type=baixa, start_date=_futuro(10), end_date=_futuro(10), half_day=True)

    def test_ferias_so_em_fim_de_semana_recusadas(self, worker, ferias):
        with pytest.raises(ValidationError, match="não tem dias úteis"):
            create_request(worker=worker, absence_type=ferias, start_date=D(2030, 6, 8), end_date=D(2030, 6, 9))

    def test_tipo_arquivado_recusado(self, worker, ferias):
        ferias.archived_at = timezone.now()
        ferias.save()
        with pytest.raises(ValidationError, match="tipo de ausência em uso"):
            create_request(worker=worker, absence_type=ferias, start_date=_futuro(10), end_date=_futuro(12))


class TestCancelamento:
    def test_cancela_pendente_e_futuro_aprovado(self, worker, ferias, manager):
        pendente = create_request(worker=worker, absence_type=ferias, start_date=_futuro(10), end_date=_futuro(12))
        cancel_request(request_obj=pendente, worker=worker)
        pendente.refresh_from_db()
        assert pendente.status == VacationRequest.Status.CANCELADO

        aprovado = create_request(
            worker=worker, absence_type=ferias, start_date=_futuro(20), end_date=_futuro(22), created_by=manager
        )
        cancel_request(request_obj=aprovado, worker=worker)
        aprovado.refresh_from_db()
        assert aprovado.status == VacationRequest.Status.CANCELADO

    def test_staff_cannot_cancel_past_absence(self, worker, ferias, manager):
        passado = create_request(
            worker=worker, absence_type=ferias, start_date=_futuro(-10), end_date=_futuro(-8), created_by=manager
        )
        with pytest.raises(ValidationError, match="já não se pode cancelar"):
            cancel_request(request_obj=passado, worker=worker)

    def test_recusado_nao_se_cancela(self, worker, ferias, manager):
        pedido = create_request(worker=worker, absence_type=ferias, start_date=_futuro(10), end_date=_futuro(12))
        decide_request(request_obj=pedido, user=manager, approve=False)
        with pytest.raises(ValidationError):
            cancel_request(request_obj=pedido, worker=worker)

    def test_cancelar_pela_vista(self, client, worker, ferias, staff_user):
        pedido = create_request(worker=worker, absence_type=ferias, start_date=_futuro(10), end_date=_futuro(12))
        client.force_login(staff_user)
        assert "Cancelar pedido" in client.get(reverse("staff:ferias")).content.decode()
        client.post(reverse("staff:cancelar_ferias", args=[pedido.pk]))
        pedido.refresh_from_db()
        assert pedido.status == VacationRequest.Status.CANCELADO

    def test_nao_cancela_pedido_alheio(self, client, restaurant, ferias, staff_user, worker):
        outro = Worker.objects.create(restaurant=restaurant, full_name="Rui")
        pedido = create_request(worker=outro, absence_type=ferias, start_date=_futuro(10), end_date=_futuro(12))
        client.force_login(staff_user)
        assert client.post(reverse("staff:cancelar_ferias", args=[pedido.pk])).status_code == 404


class TestSaldo:
    def test_balance_deducted_only_on_approval(self, worker, ferias, manager):
        ano = 2030
        assert balance(worker, ano)["disponiveis"] == 22
        pedido = create_request(worker=worker, absence_type=ferias, start_date=D(ano, 6, 3), end_date=D(ano, 6, 7))
        assert balance(worker, ano)["disponiveis"] == 22
        decide_request(request_obj=pedido, user=manager, approve=True)
        assert balance(worker, ano)["disponiveis"] == 17

    def test_tipo_que_nao_desconta(self, worker, baixa):
        create_request(worker=worker, absence_type=baixa, start_date=D(2030, 6, 3), end_date=D(2030, 6, 7))
        assert balance(worker, 2030)["disponiveis"] == 22

    def test_transitados_gastam_se_primeiro_e_caducam(self, worker, ferias, manager):
        Allowance.objects.create(
            worker=worker, year=2030, days=22, carried_over=3, carry_over_expires_on=D(2030, 4, 30)
        )
        # 2 dias em março: saem dos transitados.
        create_request(worker=worker, absence_type=ferias, start_date=D(2030, 3, 4), end_date=D(2030, 3, 5), created_by=manager)
        antes = balance(worker, 2030, on=D(2030, 4, 1))
        assert antes["disponiveis"] == 23  # 22 + 1 transitado que sobra
        depois = balance(worker, 2030, on=D(2030, 5, 2))
        assert depois["caducados"] == 1 and depois["disponiveis"] == 22

    def test_pedido_acima_do_saldo_avisa_mas_nao_bloqueia(self, client, worker, ferias, manager):
        Allowance.objects.create(worker=worker, year=2030, days=2)
        pedido = create_request(worker=worker, absence_type=ferias, start_date=D(2030, 6, 3), end_date=D(2030, 6, 7))
        client.force_login(manager)
        assert "Acima do saldo" in client.get(reverse("vacations:lista")).content.decode()
        decide_request(request_obj=pedido, user=manager, approve=True)
        assert balance(worker, 2030)["disponiveis"] == -3

    def test_editar_saldo_pela_vista(self, client, worker, manager):
        client.force_login(manager)
        assert "Marta Silva" in client.get(reverse("vacations:saldos") + "?ano=2030").content.decode()
        client.post(
            reverse("vacations:saldos"),
            {"worker": worker.pk, "ano": 2030, f"w{worker.pk}-days": "25", f"w{worker.pk}-carried_over": "2",
             f"w{worker.pk}-carry_over_expires_on": ""},
        )
        saldo = Allowance.objects.get(worker=worker, year=2030)
        assert saldo.days == 25 and saldo.carried_over == 2


class TestPeriodosBloqueados:
    def test_blocked_period_rejects_request(self, worker, ferias, restaurant):
        BlockedPeriod.objects.create(restaurant=restaurant, name="Época alta", start=_futuro(30), end=_futuro(60))
        with pytest.raises(ValidationError, match="Época alta"):
            create_request(worker=worker, absence_type=ferias, start_date=_futuro(55), end_date=_futuro(65))

    def test_so_bloqueia_os_tipos_escolhidos(self, worker, ferias, baixa, restaurant):
        periodo = BlockedPeriod.objects.create(restaurant=restaurant, name="Época alta", start=_futuro(30), end=_futuro(60))
        periodo.absence_types.add(ferias)
        create_request(worker=worker, absence_type=baixa, start_date=_futuro(40), end_date=_futuro(41))

    def test_trabalhador_isento(self, worker, ferias, restaurant):
        periodo = BlockedPeriod.objects.create(restaurant=restaurant, name="Época alta", start=_futuro(30), end=_futuro(60))
        periodo.exempt_workers.add(worker)
        create_request(worker=worker, absence_type=ferias, start_date=_futuro(40), end_date=_futuro(44))

    def test_gerente_pode_registar_no_periodo(self, worker, ferias, restaurant, manager):
        BlockedPeriod.objects.create(restaurant=restaurant, name="Época alta", start=_futuro(30), end=_futuro(60))
        create_request(worker=worker, absence_type=ferias, start_date=_futuro(40), end_date=_futuro(44), created_by=manager)

    def test_bloqueio_visivel_antes_de_pedir(self, client, restaurant, staff_user, worker):
        BlockedPeriod.objects.create(restaurant=restaurant, name="Época alta", start=_futuro(30), end=_futuro(60))
        client.force_login(staff_user)
        html = client.get(reverse("staff:ferias")).content.decode()
        assert "Sem pedidos nestas datas" in html and "Época alta" in html
