"""Fase 5: tipos de ausência, meio dia, cancelamento, saldo, feriados e
períodos bloqueados."""
import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from attendance import month as mes
from vacations.holidays import easter, national_holidays
from vacations.models import AbsenceType, Allowance, BlockedPeriod, Holiday, VacationRequest
from vacations.services import (
    balance,
    cancel_by_manager,
    cancel_request,
    count_days,
    create_request,
    decide_request,
)
from workers.models import Worker

pytestmark = pytest.mark.django_db

D = datetime.date
DIA = datetime.timedelta(days=1)


@pytest.fixture
def worker(restaurant, staff_user):
    w = Worker.objects.create(restaurant=restaurant, full_name="Marta Silva", user=staff_user)
    w.set_kiosk_code("2468")
    return w


@pytest.fixture
def ferias(restaurant):
    return AbsenceType.objects.get(restaurant=restaurant, name="Férias")


@pytest.fixture
def baixa(restaurant):
    return AbsenceType.objects.get(restaurant=restaurant, name="Baixa médica")


@pytest.fixture
def mes_passado():
    return mes.previous_month(timezone.localdate())


def proximo_dia_util(worker, dia):
    """O primeiro dia, a partir de `dia`, em que a ausência desconta um dia."""
    while count_days(worker, dia, dia) != 1:
        dia += DIA
    return dia


def primeiro_dia_util(worker, mes_inicio):
    return proximo_dia_util(worker, mes_inicio)


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


class TestMesAprovadoESobreposicao:
    def test_aprovar_em_mes_aprovado_e_recusado(self, worker, manager, ferias, mes_passado):
        mes.approve_month(worker=worker, month=mes_passado, user=manager)
        dia = primeiro_dia_util(worker, mes_passado)
        pedido = VacationRequest.objects.create(
            worker=worker, absence_type=ferias, start_date=dia, end_date=dia, days_taken=1
        )
        with pytest.raises(ValidationError, match="já foi aprovado"):
            decide_request(request_obj=pedido, user=manager, approve=True)
        pedido.refresh_from_db()
        assert pedido.status == VacationRequest.Status.PENDENTE

    def test_recusar_em_mes_aprovado_continua_possivel(self, worker, manager, ferias, mes_passado):
        mes.approve_month(worker=worker, month=mes_passado, user=manager)
        dia = primeiro_dia_util(worker, mes_passado)
        pedido = VacationRequest.objects.create(
            worker=worker, absence_type=ferias, start_date=dia, end_date=dia, days_taken=1
        )
        decide_request(request_obj=pedido, user=manager, approve=False)
        pedido.refresh_from_db()
        assert pedido.status == VacationRequest.Status.RECUSADO

    def test_gerente_nao_regista_ausencia_em_mes_aprovado(self, worker, manager, ferias, mes_passado):
        mes.approve_month(worker=worker, month=mes_passado, user=manager)
        dia = primeiro_dia_util(worker, mes_passado)
        with pytest.raises(ValidationError, match="já foi aprovado"):
            create_request(worker=worker, absence_type=ferias, start_date=dia, end_date=dia, created_by=manager)
        assert not VacationRequest.objects.filter(worker=worker).exists()

    def test_tipo_sem_aprovacao_nao_nasce_em_mes_aprovado(self, worker, manager, baixa, mes_passado):
        mes.approve_month(worker=worker, month=mes_passado, user=manager)
        dia = primeiro_dia_util(worker, mes_passado)
        with pytest.raises(ValidationError, match="já foi aprovado"):
            create_request(worker=worker, absence_type=baixa, start_date=dia, end_date=dia)

    def test_pedido_pendente_em_mes_aprovado_ainda_se_submete(self, worker, manager, ferias, mes_passado):
        mes.approve_month(worker=worker, month=mes_passado, user=manager)
        dia = primeiro_dia_util(worker, mes_passado)
        pedido = create_request(worker=worker, absence_type=ferias, start_date=dia, end_date=dia)
        assert pedido.status == VacationRequest.Status.PENDENTE

    def test_ausencia_que_atravessa_um_mes_aprovado_e_recusada(self, worker, manager, baixa, mes_passado):
        """Basta um dos meses tocados estar aprovado, mesmo não sendo o do início:
        a ausência começa no mês anterior (aberto) e entra no mês aprovado."""
        mes.approve_month(worker=worker, month=mes_passado, user=manager)
        antes = mes.previous_month(mes_passado)
        with pytest.raises(ValidationError, match="já foi aprovado"):
            create_request(
                worker=worker,
                absence_type=baixa,
                start_date=mes_passado - 2 * DIA,
                end_date=mes_passado + 2 * DIA,
                created_by=manager,
            )
        assert not mes.is_closed(worker, antes)
        assert not VacationRequest.objects.filter(worker=worker).exists()

    def test_cancelar_ausencia_que_so_toca_num_mes_aprovado_depois_do_inicio(
        self, worker, manager, baixa, mes_passado
    ):
        """A ausência começa no mês anterior (aberto), atravessa o mês aprovado
        e acaba no mês corrente: cancelar muda o mês aprovado."""
        pedido = create_request(
            worker=worker,
            absence_type=baixa,
            start_date=mes_passado - 2 * DIA,
            end_date=timezone.localdate() + 3 * DIA,
            created_by=manager,
        )
        assert pedido.status == VacationRequest.Status.APROVADO
        mes.approve_month(worker=worker, month=mes_passado, user=manager)
        assert not mes.is_closed(worker, pedido.start_date)
        with pytest.raises(ValidationError, match="já foi aprovado"):
            cancel_by_manager(request_obj=pedido, user=manager)
        pedido.refresh_from_db()
        assert pedido.status == VacationRequest.Status.APROVADO

    def test_cancelar_ausencia_aprovada_respeita_mes_aprovado(self, worker, manager, ferias, mes_passado):
        dia = primeiro_dia_util(worker, mes_passado)
        pedido = VacationRequest.objects.create(
            worker=worker,
            absence_type=ferias,
            start_date=dia,
            end_date=timezone.localdate() + 3 * DIA,
            days_taken=1,
            status=VacationRequest.Status.APROVADO,
        )
        mes.approve_month(worker=worker, month=mes_passado, user=manager)
        with pytest.raises(ValidationError, match="já foi aprovado"):
            cancel_by_manager(request_obj=pedido, user=manager)
        pedido.refresh_from_db()
        assert pedido.status == VacationRequest.Status.APROVADO

    def test_aprovar_sobreposta_a_aprovada_e_recusado_e_o_saldo_desce_uma_vez(self, worker, manager, ferias):
        inicio = proximo_dia_util(worker, timezone.localdate() + datetime.timedelta(days=20))
        create_request(
            worker=worker, absence_type=ferias, start_date=inicio, end_date=inicio + 2 * DIA, created_by=manager
        )
        saldo = balance(worker, inicio.year)
        # Começa no mesmo dia útil, para o pedido ter sempre dias a descontar.
        pedido = create_request(worker=worker, absence_type=ferias, start_date=inicio, end_date=inicio + 3 * DIA)
        assert pedido.status == VacationRequest.Status.PENDENTE
        with pytest.raises(ValidationError, match="Sobrepõe-se") as erro:
            decide_request(request_obj=pedido, user=manager, approve=True)
        assert erro.value.messages[0] == (
            f"Sobrepõe-se a Férias de {inicio:%d/%m} a {inicio + 2 * DIA:%d/%m}, já aprovada. "
            "Recuse este pedido ou cancele a outra ausência."
        )
        assert balance(worker, inicio.year) == saldo

    def test_tipo_sem_aprovacao_sobreposto_e_recusado(self, worker, manager, ferias, baixa):
        inicio = proximo_dia_util(worker, timezone.localdate() + datetime.timedelta(days=20))
        create_request(
            worker=worker, absence_type=ferias, start_date=inicio, end_date=inicio + 2 * DIA, created_by=manager
        )
        fim = inicio + 2 * DIA
        with pytest.raises(ValidationError, match="Sobrepõe-se"):
            create_request(worker=worker, absence_type=baixa, start_date=fim, end_date=fim + 2 * DIA)
        assert VacationRequest.objects.filter(worker=worker).count() == 1

    def test_dias_seguidos_sem_cruzar_nao_se_sobrepoem(self, worker, manager, ferias):
        inicio = proximo_dia_util(worker, timezone.localdate() + datetime.timedelta(days=20))
        create_request(worker=worker, absence_type=ferias, start_date=inicio, end_date=inicio, created_by=manager)
        seguinte = proximo_dia_util(worker, inicio + DIA)
        create_request(worker=worker, absence_type=ferias, start_date=seguinte, end_date=seguinte, created_by=manager)
        assert VacationRequest.objects.filter(worker=worker).count() == 2

    def test_pedido_pendente_sobreposto_ainda_se_submete(self, worker, manager, ferias):
        inicio = proximo_dia_util(worker, timezone.localdate() + datetime.timedelta(days=20))
        create_request(
            worker=worker, absence_type=ferias, start_date=inicio, end_date=inicio + 2 * DIA, created_by=manager
        )
        pedido = create_request(worker=worker, absence_type=ferias, start_date=inicio, end_date=inicio + DIA)
        assert pedido.status == VacationRequest.Status.PENDENTE

    def test_recusar_pedido_sobreposto_continua_possivel(self, worker, manager, ferias):
        inicio = proximo_dia_util(worker, timezone.localdate() + datetime.timedelta(days=20))
        create_request(
            worker=worker, absence_type=ferias, start_date=inicio, end_date=inicio + 2 * DIA, created_by=manager
        )
        pedido = create_request(worker=worker, absence_type=ferias, start_date=inicio, end_date=inicio + DIA)
        decide_request(request_obj=pedido, user=manager, approve=False)
        pedido.refresh_from_db()
        assert pedido.status == VacationRequest.Status.RECUSADO

    def test_ausencia_cancelada_nao_conta_como_sobreposicao(self, worker, manager, ferias):
        inicio = proximo_dia_util(worker, timezone.localdate() + datetime.timedelta(days=20))
        primeira = create_request(
            worker=worker, absence_type=ferias, start_date=inicio, end_date=inicio + 2 * DIA, created_by=manager
        )
        pedido = create_request(worker=worker, absence_type=ferias, start_date=inicio, end_date=inicio + DIA)
        cancel_by_manager(request_obj=primeira, user=manager)
        decide_request(request_obj=pedido, user=manager, approve=True)
        pedido.refresh_from_db()
        assert pedido.status == VacationRequest.Status.APROVADO


def test_pendente_com_datas_passadas_assinalado(client, manager, restaurant):
    w = Worker.objects.create(restaurant=restaurant, full_name="Rui Atrasado")
    tipo = AbsenceType.objects.get(restaurant=restaurant, name="Férias")
    ontem = timezone.localdate() - datetime.timedelta(days=1)
    VacationRequest.objects.create(worker=w, absence_type=tipo, start_date=ontem, end_date=ontem)
    client.force_login(manager)
    assert "Datas já passaram" in client.get(reverse("vacations:lista")).content.decode()


def test_dashboard_conta_pendentes_com_datas_passadas(client, manager, restaurant):
    from sales.services import dia_de_servico

    hoje = dia_de_servico(restaurant)  # o «hoje» do dashboard
    dia = datetime.timedelta(days=1)
    tipo = AbsenceType.objects.get(restaurant=restaurant, name="Férias")
    passado = Worker.objects.create(restaurant=restaurant, full_name="Rui Passado")
    futuro = Worker.objects.create(restaurant=restaurant, full_name="Ana Futura")
    VacationRequest.objects.create(worker=passado, absence_type=tipo, start_date=hoje - 2 * dia, end_date=hoje - dia)
    VacationRequest.objects.create(worker=futuro, absence_type=tipo, start_date=hoje + 3 * dia, end_date=hoje + 5 * dia)
    client.force_login(manager)
    html = client.get(reverse("dashboard:home")).content.decode()
    assert (
        '<span class="font-dados font-semibold">2</span> pedidos de férias por decidir, '
        '<span class="font-dados font-semibold">1</span> com datas passadas'
    ) in html
