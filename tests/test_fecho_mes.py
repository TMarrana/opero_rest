"""Fase 5: fecho do mês, bloqueio, reabertura e exportação."""
import datetime
import zoneinfo

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from attendance import month as mes
from attendance.models import BreakType, CorrectionRequest, MonthClose
from attendance.services import (
    add_manual_entry,
    close_shift,
    correct_entry,
    decide_correction,
    end_break,
    open_shift,
    request_correction,
    start_break,
)
from workers.models import Worker

pytestmark = pytest.mark.django_db

LISBOA = zoneinfo.ZoneInfo("Europe/Lisbon")
H = datetime.timedelta(hours=1)


def _local(*args):
    return datetime.datetime(*args, tzinfo=LISBOA)


@pytest.fixture
def worker(restaurant, staff_user):
    staff_user.set_staff_pin("2468")
    return Worker.objects.create(restaurant=restaurant, full_name="Marta Silva", user=staff_user)


@pytest.fixture
def mes_passado():
    return mes.previous_month(timezone.localdate())


def _dia(mes_inicio, dia, hora=9):
    return _local(mes_inicio.year, mes_inicio.month, dia, hora, 0)


class TestAprovacao:
    def test_aprova_mes_sem_pendentes(self, worker, manager, mes_passado):
        open_shift(worker=worker, at=_dia(mes_passado, 10))
        close_shift(worker=worker, at=_dia(mes_passado, 10, 17))
        fecho = mes.approve_month(worker=worker, month=mes_passado, user=manager)
        assert fecho.month == mes_passado and fecho.approved_by == manager
        assert mes.is_closed(worker, _dia(mes_passado, 20).date())

    def test_month_approval_lists_unresolved(self, worker, manager, mes_passado):
        open_shift(worker=worker, at=_dia(mes_passado, 10))  # nunca saiu
        with pytest.raises(ValidationError, match="1 registo"):
            mes.approve_month(worker=worker, month=mes_passado, user=manager)

    def test_pedido_pendente_impede(self, worker, manager, mes_passado):
        request_correction(worker=worker, note="esqueci", check_in=_dia(mes_passado, 11), check_out=_dia(mes_passado, 11, 17))
        with pytest.raises(ValidationError, match="1 pedido"):
            mes.approve_month(worker=worker, month=mes_passado, user=manager)

    def test_mes_atual_nao_se_aprova(self, worker, manager):
        with pytest.raises(ValidationError, match="já terminou"):
            mes.approve_month(worker=worker, month=timezone.localdate(), user=manager)

    def test_aprovar_todos_os_prontos(self, restaurant, worker, manager, mes_passado):
        outro = Worker.objects.create(restaurant=restaurant, full_name="Rui")
        open_shift(worker=outro, at=_dia(mes_passado, 10))
        aprovados, recusados = mes.approve_ready(workers=[worker, outro], month=mes_passado, user=manager)
        assert aprovados == [worker]
        assert recusados[0][0] == outro and "por resolver" in recusados[0][1]


class TestBloqueio:
    def test_approved_month_is_locked(self, worker, manager, mes_passado):
        """Invariante 8: um mês aprovado recusa correções e registos manuais."""
        entry = open_shift(worker=worker, at=_dia(mes_passado, 10))
        close_shift(worker=worker, at=_dia(mes_passado, 10, 17))
        mes.approve_month(worker=worker, month=mes_passado, user=manager)
        with pytest.raises(ValidationError, match="já foi aprovado"):
            correct_entry(entry=entry, user=manager, reason="x", check_out=_dia(mes_passado, 10, 18))
        with pytest.raises(ValidationError, match="já foi aprovado"):
            add_manual_entry(worker=worker, user=manager, reason="x", check_in=_dia(mes_passado, 12), check_out=_dia(mes_passado, 12, 17))
        with pytest.raises(ValidationError, match="já foi aprovado"):
            request_correction(worker=worker, entry=entry, note="x", check_in=_dia(mes_passado, 10, 8), check_out=_dia(mes_passado, 10, 17))
        with pytest.raises(ValidationError, match="já foi aprovado"):
            open_shift(worker=worker, at=_dia(mes_passado, 25))  # marcação offline atrasada

    def test_nao_move_registo_para_mes_aprovado(self, worker, manager, mes_passado):
        mes.approve_month(worker=worker, month=mes_passado, user=manager)
        entry = open_shift(worker=worker, at=timezone.now() - 2 * H)
        with pytest.raises(ValidationError, match="já foi aprovado"):
            correct_entry(entry=entry, user=manager, reason="x", check_in=_dia(mes_passado, 10), check_out=_dia(mes_passado, 10, 17))

    def test_reabrir_exige_motivo_e_desbloqueia(self, worker, manager, mes_passado):
        entry = open_shift(worker=worker, at=_dia(mes_passado, 10))
        close_shift(worker=worker, at=_dia(mes_passado, 10, 17))
        mes.approve_month(worker=worker, month=mes_passado, user=manager)
        with pytest.raises(ValidationError, match="motivo"):
            mes.reopen_month(worker=worker, month=mes_passado, user=manager, reason=" ")
        fecho = mes.reopen_month(worker=worker, month=mes_passado, user=manager, reason="erro na saída do dia 10")
        assert fecho.reopened_by == manager
        correct_entry(entry=entry, user=manager, reason="saída certa", check_out=_dia(mes_passado, 10, 18))
        novo = mes.approve_month(worker=worker, month=mes_passado, user=manager)
        assert MonthClose.objects.filter(worker=worker, month=mes_passado).count() == 2
        assert novo.reopened_at is None


class TestExportacao:
    def test_csv_so_com_aprovados_e_pausas_descontadas(self, restaurant, worker, manager, mes_passado):
        outro = Worker.objects.create(restaurant=restaurant, full_name="Rui Por Aprovar")
        refeicao = BreakType.objects.get(restaurant=restaurant, name="Refeição")
        open_shift(worker=worker, at=_dia(mes_passado, 10))
        start_break(worker=worker, break_type=refeicao, at=_dia(mes_passado, 10, 13))
        end_break(worker=worker, at=_dia(mes_passado, 10, 14))
        close_shift(worker=worker, at=_dia(mes_passado, 10, 18))
        open_shift(worker=outro, at=_dia(mes_passado, 10))
        close_shift(worker=outro, at=_dia(mes_passado, 10, 17))
        mes.approve_month(worker=worker, month=mes_passado, user=manager)

        csv = mes.export_csv([worker, outro], mes_passado)
        assert "Marta Silva;" in csv
        assert "Rui Por Aprovar" not in csv
        assert ";09:00;18:00;1:00;8:00;" in csv
        assert csv.rstrip().endswith("Marta Silva;;;;;8:00")

    def test_exportar_pela_vista(self, client, worker, manager, mes_passado):
        open_shift(worker=worker, at=_dia(mes_passado, 10))
        close_shift(worker=worker, at=_dia(mes_passado, 10, 17))
        client.force_login(manager)
        resp = client.post(reverse("attendance:mes"), {"mes": f"{mes_passado:%Y-%m}", "acao": "aprovar_todos"})
        assert resp.status_code == 302
        resp = client.get(reverse("attendance:mes") + f"?mes={mes_passado:%Y-%m}&exportar=1")
        assert resp["Content-Type"].startswith("text/csv")
        assert "Marta Silva" in resp.content.decode("utf-8-sig")

    def test_dashboard_avisa_mes_por_fechar(self, client, worker, manager, mes_passado):
        client.force_login(manager)
        html = client.get(reverse("dashboard:home")).content.decode()
        assert "está por fechar" in html
        mes.approve_month(worker=worker, month=mes_passado, user=manager)
        assert "está por fechar" not in client.get(reverse("dashboard:home")).content.decode()


def test_aceitacao_fase_5(client, restaurant, worker, manager, mes_passado):
    """Aceitação da Fase 5: entrada, pausa não paga e saída num turno que
    passa a meia-noite; o gerente vê o turno num só dia com a pausa
    descontada; o colaborador pede uma correção que o gerente aprova, e o
    valor anterior fica no histórico; o gerente aprova e exporta o mês, e
    a partir daí o mês recusa alterações."""
    refeicao = BreakType.objects.get(restaurant=restaurant, name="Refeição")
    entry = open_shift(worker=worker, at=_dia(mes_passado, 14, 19))
    start_break(worker=worker, break_type=refeicao, at=_dia(mes_passado, 14, 22))
    end_break(worker=worker, at=_dia(mes_passado, 14, 23))
    close_shift(worker=worker, at=_dia(mes_passado, 15, 2))

    client.force_login(manager)
    dia_14 = client.get(reverse("attendance:dia") + f"?dia={_dia(mes_passado, 14).date()}").content.decode()
    dia_15 = client.get(reverse("attendance:dia") + f"?dia={_dia(mes_passado, 15).date()}").content.decode()
    assert "6h00" in dia_14 and "19:00" in dia_14
    assert "19:00" not in dia_15

    pedido = request_correction(
        worker=worker, entry=entry, note="saí às 2h30", check_in=_dia(mes_passado, 14, 19),
        check_out=_local(mes_passado.year, mes_passado.month, 15, 2, 30),
    )
    decide_correction(request_obj=pedido, user=manager, approve=True)
    correcao = entry.corrections.get()
    assert correcao.old_check_out == _dia(mes_passado, 15, 2)
    assert pedido.__class__.objects.get().status == CorrectionRequest.Status.APROVADO

    client.post(reverse("attendance:mes"), {"mes": f"{mes_passado:%Y-%m}", "acao": "aprovar_todos"})
    csv = client.get(reverse("attendance:mes") + f"?mes={mes_passado:%Y-%m}&exportar=1").content.decode("utf-8-sig")
    assert ";19:00;02:30;1:00;6:30;" in csv
    with pytest.raises(ValidationError, match="já foi aprovado"):
        correct_entry(entry=entry, user=manager, reason="x", check_out=_dia(mes_passado, 15, 3))
