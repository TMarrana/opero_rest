"""Fase 5: pedidos de correção do colaborador e registos por resolver."""
import datetime

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from attendance.models import CorrectionRequest, EntryCorrection, TimeEntry
from attendance.services import (
    close_shift,
    decide_correction,
    open_shift,
    request_correction,
)
from workers.models import Worker

pytestmark = pytest.mark.django_db

H = datetime.timedelta(hours=1)


@pytest.fixture
def worker(restaurant, staff_user):
    w = Worker.objects.create(restaurant=restaurant, full_name="Marta Silva", user=staff_user)
    w.set_kiosk_code("2468")
    return w


@pytest.fixture
def outro(restaurant):
    return Worker.objects.create(restaurant=restaurant, full_name="Rui Costa")


def _turno(worker, inicio, horas=8):
    open_shift(worker=worker, at=inicio)
    return close_shift(worker=worker, at=inicio + horas * H)


def _entrar_na_app(client, manager, worker):
    client.force_login(worker.user)


class TestPorResolver:
    def test_unresolved_entry_excluded_from_total(self, worker):
        """Invariante 9: uma entrada sem saída que passou do limite (14 h)
        não conta para os totais."""
        entry = open_shift(worker=worker, at=timezone.now() - 20 * H)
        assert entry.is_unresolved()
        assert entry.worked() == datetime.timedelta()
        assert TimeEntry.objects.unresolved().get() == entry

    def test_turno_aberto_dentro_do_limite_conta(self, worker):
        entry = open_shift(worker=worker, at=timezone.now() - 3 * H)
        assert not entry.is_unresolved()
        assert entry.worked() >= 3 * H - datetime.timedelta(minutes=1)

    def test_entrada_nova_poe_de_lado_a_esquecida(self, worker):
        antiga = open_shift(worker=worker, at=timezone.now() - 20 * H)
        nova = open_shift(worker=worker)
        antiga.refresh_from_db()
        assert antiga.missing_exit and antiga.check_out is None
        assert worker.open_entry == nova
        assert TimeEntry.objects.unresolved().get() == antiga

    def test_entrada_dupla_dentro_do_limite_continua_recusada(self, worker):
        open_shift(worker=worker, at=timezone.now() - 2 * H)
        with pytest.raises(ValidationError, match="já tem um turno aberto"):
            open_shift(worker=worker)

    def test_saida_depois_do_limite_recusada(self, worker):
        open_shift(worker=worker, at=timezone.now() - 20 * H)
        with pytest.raises(ValidationError, match="Peça uma correção"):
            close_shift(worker=worker)

    def test_app_mostra_aviso_de_saida_por_indicar(self, client, manager, worker):
        antiga = open_shift(worker=worker, at=timezone.now() - 20 * H)
        _entrar_na_app(client, manager, worker)
        html = client.get(reverse("staff:home")).content.decode()
        assert "Saída por indicar" in html
        assert reverse("staff:correcao", args=[antiga.pk]) in html

    def test_correcao_resolve(self, worker, manager):
        from attendance.services import correct_entry

        antiga = open_shift(worker=worker, at=timezone.now() - 20 * H)
        open_shift(worker=worker)
        with pytest.raises(ValidationError, match="indique a hora de saída"):
            correct_entry(entry=antiga, user=manager, reason="x", check_in=antiga.check_in)
        correct_entry(entry=antiga, user=manager, reason="saiu às 8h depois", check_out=antiga.check_in + 8 * H)
        antiga.refresh_from_db()
        assert not antiga.missing_exit and not antiga.is_unresolved()
        assert antiga.worked() == 8 * H

    def test_dashboard_conta_por_resolver(self, client, manager, worker):
        open_shift(worker=worker, at=timezone.now() - 20 * H)
        client.force_login(manager)
        html = client.get(reverse("dashboard:home")).content.decode()
        assert "registo de ponto por resolver" in html
        assert "Ninguém em turno" in html


class TestPedidosDeCorrecao:
    def test_pedido_de_alteracao_e_aprovacao(self, worker, manager):
        inicio = timezone.now() - 30 * H
        entry = _turno(worker, inicio)
        pedido = request_correction(
            worker=worker, entry=entry, note="entrei mais cedo",
            check_in=inicio - H, check_out=inicio + 8 * H,
        )
        assert pedido.status == CorrectionRequest.Status.PENDENTE
        entry.refresh_from_db()
        assert entry.check_in == inicio  # nada muda até o gerente decidir

        decide_correction(request_obj=pedido, user=manager, approve=True, note="ok")
        entry.refresh_from_db()
        pedido.refresh_from_db()
        assert entry.check_in == inicio - H
        assert pedido.status == CorrectionRequest.Status.APROVADO and pedido.decided_by == manager
        correcao = entry.corrections.get()
        assert correcao.old_check_in == inicio and correcao.new_check_in == inicio - H
        assert "entrei mais cedo" in correcao.reason

    def test_pedido_de_registo_em_falta(self, worker, manager):
        inicio = timezone.now() - 50 * H
        pedido = request_correction(worker=worker, note="não marquei", check_in=inicio, check_out=inicio + 6 * H)
        decide_correction(request_obj=pedido, user=manager, approve=True)
        pedido.refresh_from_db()
        assert pedido.entry.check_out == inicio + 6 * H
        assert pedido.entry.corrections.get().kind == EntryCorrection.Kind.CRIAR

    def test_recusa_nao_altera_registo(self, worker, manager):
        inicio = timezone.now() - 30 * H
        entry = _turno(worker, inicio)
        pedido = request_correction(worker=worker, entry=entry, note="x", check_in=inicio, check_out=inicio + 10 * H)
        decide_correction(request_obj=pedido, user=manager, approve=False, note="saiu às 8h")
        entry.refresh_from_db()
        assert entry.check_out == inicio + 8 * H
        assert not entry.corrections.exists()
        with pytest.raises(ValidationError, match="já foi decidido"):
            decide_correction(request_obj=pedido, user=manager, approve=True)

    def test_so_um_pedido_pendente_por_registo(self, worker):
        inicio = timezone.now() - 30 * H
        entry = _turno(worker, inicio)
        request_correction(worker=worker, entry=entry, note="a", check_in=inicio, check_out=inicio + 9 * H)
        with pytest.raises(ValidationError, match="Já há um pedido pendente"):
            request_correction(worker=worker, entry=entry, note="b", check_in=inicio, check_out=inicio + 9 * H)

    def test_nao_pede_correcao_de_registo_alheio(self, worker, outro):
        inicio = timezone.now() - 30 * H
        entry = _turno(outro, inicio)
        with pytest.raises(ValidationError, match="seus registos"):
            request_correction(worker=worker, entry=entry, note="a", check_in=inicio, check_out=inicio + H)

    def test_saida_no_futuro_recusada(self, worker):
        with pytest.raises(ValidationError, match="futuro"):
            request_correction(worker=worker, note="a", check_in=timezone.now(), check_out=timezone.now() + H)

    def test_pedido_aplica_os_valores_propostos_mesmo_depois_de_outra_correcao(self, worker, manager):
        """O pedido propõe entrada e saída completas. Se o gerente corrigiu
        o registo entretanto, aprovar aplica o proposto por cima, e as duas
        correções ficam no histórico."""
        inicio = timezone.now() - 30 * H
        entry = _turno(worker, inicio)
        pedido = request_correction(worker=worker, entry=entry, note="a", check_in=inicio, check_out=inicio + 9 * H)
        # Entretanto o gerente corrigiu a entrada para depois da saída proposta.
        from attendance.services import correct_entry

        correct_entry(entry=entry, user=manager, reason="b", check_in=inicio + 10 * H, check_out=inicio + 11 * H)
        decide_correction(request_obj=pedido, user=manager, approve=True)
        entry.refresh_from_db()
        assert entry.check_in == inicio and entry.check_out == inicio + 9 * H
        assert entry.corrections.count() == 2

    def test_fluxo_completo_pelas_vistas(self, client, manager, worker):
        inicio = timezone.now() - 30 * H
        entry = _turno(worker, inicio)
        _entrar_na_app(client, manager, worker)
        html = client.get(reverse("staff:historico")).content.decode()
        assert reverse("staff:correcao", args=[entry.pk]) in html

        fmt = "%Y-%m-%dT%H:%M"
        resp = client.post(
            reverse("staff:correcao", args=[entry.pk]),
            {
                "check_in": timezone.localtime(inicio - H).strftime(fmt),
                "check_out": timezone.localtime(inicio + 8 * H).strftime(fmt),
                "note": "entrei às 8h",
            },
        )
        assert resp.status_code == 302
        assert "correção pendente" in client.get(reverse("staff:historico")).content.decode()

        client.force_login(manager)
        assert "pedido de correção por decidir" in client.get(reverse("attendance:dia")).content.decode()
        html = client.get(reverse("attendance:pedidos")).content.decode()
        assert "entrei às 8h" in html
        pedido = CorrectionRequest.objects.get()
        client.post(reverse("attendance:decidir_pedido", args=[pedido.pk, "aprovar"]), {"decision_note": ""})
        pedido.refresh_from_db()
        assert pedido.status == CorrectionRequest.Status.APROVADO

    def test_colaborador_nao_pede_sobre_registo_alheio_pela_vista(self, client, manager, worker, outro):
        entry = _turno(outro, timezone.now() - 30 * H)
        _entrar_na_app(client, manager, worker)
        assert client.get(reverse("staff:correcao", args=[entry.pk])).status_code == 404

    def test_colaborador_nao_abre_lista_de_pedidos(self, client, manager, worker):
        _entrar_na_app(client, manager, worker)
        assert client.get(reverse("attendance:pedidos")).status_code == 403
