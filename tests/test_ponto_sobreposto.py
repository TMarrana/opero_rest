"""Ponto (2026-11-04): os registos de uma pessoa não se sobrepõem, e o
gerente pode apagar um registo que seja um erro (fica guardado, fora das
listas e dos totais)."""
import datetime

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from attendance.models import CorrectionRequest, EntryCorrection, MonthClose, TimeEntry
from attendance.services import (
    add_manual_entry,
    annul_entry,
    close_shift,
    correct_entry,
    open_shift,
    overlapping,
    request_correction,
)
from workers.models import Worker

pytestmark = pytest.mark.django_db
H = datetime.timedelta(hours=1)


def ontem(h, m=0):
    dia = timezone.localdate() - datetime.timedelta(days=1)
    return timezone.make_aware(datetime.datetime.combine(dia, datetime.time(h, m)))


@pytest.fixture
def ana(restaurant):
    return Worker.objects.create(restaurant=restaurant, full_name="Ana Lopes")


@pytest.fixture
def turno(ana, manager):
    return add_manual_entry(worker=ana, user=manager, check_in=ontem(9), check_out=ontem(17))


def _bruto(worker, inicio, fim):
    """Um registo gravado sem passar pelos serviços (como os duplicados
    antigos que já estão na base de dados)."""
    return TimeEntry.objects.create(worker=worker, restaurant=worker.restaurant, check_in=inicio, check_out=fim)


class TestSemSobreposicao:
    def test_acrescentar_por_cima_recusa(self, ana, manager, turno):
        with pytest.raises(ValidationError, match="Sobrepõe-se"):
            add_manual_entry(worker=ana, user=manager, check_in=ontem(16), check_out=ontem(20))
        with pytest.raises(ValidationError, match="Sobrepõe-se"):
            add_manual_entry(worker=ana, user=manager, check_in=ontem(9), check_out=ontem(17))  # duplicado
        with pytest.raises(ValidationError, match="Sobrepõe-se"):
            add_manual_entry(worker=ana, user=manager, check_in=ontem(10), check_out=ontem(11))  # dentro

    def test_encostados_aceita(self, ana, manager, turno):
        add_manual_entry(worker=ana, user=manager, check_in=ontem(17), check_out=ontem(22))
        add_manual_entry(worker=ana, user=manager, check_in=ontem(7), check_out=ontem(9))
        assert TimeEntry.objects.filter(worker=ana).count() == 3

    def test_corrigir_para_cima_de_outro_recusa(self, ana, manager, turno):
        tarde = add_manual_entry(worker=ana, user=manager, check_in=ontem(18), check_out=ontem(22))
        with pytest.raises(ValidationError, match="Sobrepõe-se"):
            correct_entry(entry=tarde, user=manager, check_in=ontem(16), check_out=ontem(22))
        correct_entry(entry=tarde, user=manager, check_in=ontem(17, 30), check_out=ontem(22))

    def test_sem_saida_vai_ate_ao_fim(self, ana, manager, turno):
        with pytest.raises(ValidationError, match="Sobrepõe-se"):
            add_manual_entry(worker=ana, user=manager, check_in=ontem(8))

    def test_noutra_casa_tambem_conta(self, ana, manager, turno):
        from core.models import Restaurant

        outra = Restaurant.objects.create(name="Outra casa", slug="outra-casa")
        ana.other_restaurants.add(outra)
        with pytest.raises(ValidationError, match="Sobrepõe-se"):
            add_manual_entry(worker=ana, user=manager, check_in=ontem(12), check_out=ontem(14), restaurant=outra)

    def test_pedido_do_colaborador_recusa(self, ana, turno):
        with pytest.raises(ValidationError, match="Sobrepõe-se"):
            request_correction(worker=ana, note="esqueci-me", check_in=ontem(15), check_out=ontem(19))
        # Alterar o próprio registo não choca consigo mesmo.
        request_correction(worker=ana, entry=turno, note="saí mais tarde", check_in=ontem(9), check_out=ontem(18))

    def test_entrada_dentro_de_um_registo_fechado_recusa(self, ana, manager):
        add_manual_entry(worker=ana, user=manager, check_in=timezone.now() - 2 * H, check_out=timezone.now() + H)
        with pytest.raises(ValidationError, match="Sobrepõe-se"):
            open_shift(worker=ana)

    def test_picar_normal_continua(self, ana, turno):
        open_shift(worker=ana)
        close_shift(worker=ana, at=timezone.now() + H)

    def test_por_resolver_nao_bloqueia_o_resto_do_dia(self, ana, manager):
        """Uma entrada sem saída posta de lado ocupa só o instante da entrada:
        pode-se acrescentar o turno seguinte e depois indicar a saída."""
        esquecida = add_manual_entry(worker=ana, user=manager, check_in=ontem(3))
        open_shift(worker=ana, at=ontem(18))  # a anterior fica por resolver
        with pytest.raises(ValidationError, match="Sobrepõe-se"):
            correct_entry(entry=esquecida, user=manager, check_out=ontem(19))
        correct_entry(entry=esquecida, user=manager, check_out=ontem(17))


class TestDetetarSobrepostos:
    def test_duplicado_e_encaixado(self, ana, turno):
        dup = _bruto(ana, ontem(9), ontem(17))
        dentro = _bruto(ana, ontem(12), ontem(13))
        depois = _bruto(ana, ontem(17), ontem(20))
        assert overlapping(TimeEntry.objects.all()) == {turno.pk, dup.pk, dentro.pk}
        assert depois.pk not in overlapping(TimeEntry.objects.all())

    def test_dashboard_e_pedidos_avisam(self, client, manager, ana, turno):
        _bruto(ana, ontem(9), ontem(17))
        client.force_login(manager)
        html = client.get(reverse("dashboard:home")).content.decode()
        assert "registos de ponto sobrepostos" in html
        html = client.get(reverse("attendance:pedidos")).content.decode()
        assert 'id="sobrepostos"' in html and "Registos sobrepostos" in html
        html = client.get(reverse("attendance:dia") + f"?dia={ontem(9).date().isoformat()}").content.decode()
        assert html.count(">sobreposto</span>") == 2

    def test_sem_sobrepostos_sem_aviso(self, client, manager, turno):
        client.force_login(manager)
        assert "sobreposto" not in client.get(reverse("dashboard:home")).content.decode()


class TestApagar:
    def test_apaga_e_fica_guardado(self, client, manager, ana, turno):
        dup = _bruto(ana, ontem(9), ontem(17))
        client.force_login(manager)
        html = client.get(reverse("attendance:corrigir", args=[dup.pk]) + "?apagar=1").content.decode()
        assert "Apagar este registo?" in html and "aberto: true" in html and "sobrepõe-se a outro" in html
        resp = client.post(reverse("attendance:apagar", args=[dup.pk]), {"reason": "Duplicado"})
        assert resp.status_code == 302
        assert not TimeEntry.objects.filter(pk=dup.pk).exists()
        guardado = TimeEntry.all_objects.get(pk=dup.pk)
        assert guardado.annulled_by == manager and guardado.annulled_at is not None
        c = EntryCorrection.objects.get(entry=guardado)
        assert (c.kind, c.reason, c.corrected_by) == (EntryCorrection.Kind.APAGAR, "Duplicado", manager)
        assert overlapping(TimeEntry.objects.all()) == set()
        # Já não conta: a página do registo dá 404 e o turno certo continua.
        assert client.get(reverse("attendance:corrigir", args=[dup.pk])).status_code == 404
        assert list(ana.time_entries.all()) == [turno]

    def test_motivo_opcional(self, manager, turno):
        annul_entry(entry=turno, user=manager)
        assert TimeEntry.all_objects.get(pk=turno.pk).annulled_at is not None

    def test_apagar_turno_aberto_deixa_picar_de_novo(self, ana, manager):
        aberto = open_shift(worker=ana)
        annul_entry(entry=aberto, user=manager)
        open_shift(worker=ana)
        assert TimeEntry.objects.filter(worker=ana, check_out__isnull=True).count() == 1

    def test_pedido_pendente_fica_recusado(self, ana, manager, turno):
        pedido = request_correction(worker=ana, entry=turno, note="saí mais tarde", check_in=ontem(9), check_out=ontem(18))
        annul_entry(entry=turno, user=manager)
        pedido.refresh_from_db()
        assert pedido.status == CorrectionRequest.Status.RECUSADO and pedido.decision_note == "O registo foi apagado."

    def test_mes_aprovado_nao_deixa(self, client, ana, manager, turno):
        MonthClose.objects.create(restaurant=ana.restaurant, worker=ana, month=turno.work_date.replace(day=1), approved_by=manager)
        with pytest.raises(ValidationError, match="já foi aprovado"):
            annul_entry(entry=turno, user=manager)
        client.force_login(manager)
        html = client.get(reverse("attendance:corrigir", args=[turno.pk])).content.decode()
        assert "Não é possível apagar" in html

    def test_colaborador_nao_apaga(self, client, staff_user, turno):
        client.force_login(staff_user)
        assert client.post(reverse("attendance:apagar", args=[turno.pk])).status_code == 403
        assert TimeEntry.objects.filter(pk=turno.pk).exists()

    def test_ficha_com_registo_apagado_nao_se_elimina(self, ana, manager, turno):
        from workers.services import delete_blockers

        annul_entry(entry=turno, user=manager)
        assert delete_blockers(ana) == ["1 registo de ponto"]
