"""Fase 2: trabalhadores, ponto e férias — invariantes 3, 4, 5 e 6."""
import datetime

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from attendance.models import TimeEntry
from attendance.services import add_manual_entry, close_shift, correct_entry, open_shift
from vacations.models import VacationRequest
from vacations.services import decide_request
from workers.models import Worker

pytestmark = pytest.mark.django_db


@pytest.fixture
def worker(restaurant):
    return Worker.objects.create(restaurant=restaurant, full_name="Marta Silva", job_title="sala")


@pytest.fixture
def outro_worker(restaurant):
    return Worker.objects.create(restaurant=restaurant, full_name="Rui Gomes", job_title="cozinha")


class TestTurnos:
    def test_entrada_e_saida(self, worker):
        entry = open_shift(worker=worker, at=timezone.now() - datetime.timedelta(hours=1))
        assert entry.is_open
        fechado = close_shift(worker=worker)
        assert fechado.pk == entry.pk
        assert fechado.check_out is not None
        assert fechado.duration.total_seconds() > 0

    def test_double_open_shift_rejected(self, worker):
        """Invariante 3: um trabalhador não pode ter dois turnos abertos."""
        open_shift(worker=worker)
        with pytest.raises(ValidationError):
            open_shift(worker=worker)
        assert worker.time_entries.count() == 1

    def test_checkout_without_checkin_rejected(self, worker):
        """Invariante 4: não há saída sem entrada prévia."""
        with pytest.raises(ValidationError):
            close_shift(worker=worker)
        assert worker.time_entries.count() == 0

    def test_saida_antes_da_entrada_rejeitada(self, worker):
        open_shift(worker=worker)
        with pytest.raises(ValidationError):
            close_shift(worker=worker, at=timezone.now() - datetime.timedelta(hours=1))

    def test_constraint_na_bd(self, worker):
        """A invariante 3 também vive na base de dados, não só no serviço."""
        from django.db import IntegrityError, transaction

        TimeEntry.objects.create(worker=worker, check_in=timezone.now())
        with pytest.raises(IntegrityError), transaction.atomic():
            TimeEntry.objects.create(worker=worker, check_in=timezone.now())


class TestCorrecoes:
    def test_correcao_exige_motivo(self, worker, manager):
        entry = open_shift(worker=worker)
        with pytest.raises(ValidationError):
            correct_entry(entry=entry, user=manager, reason="  ")

    def test_correcao_guarda_autor_motivo_e_data(self, worker, manager):
        """Invariante 5 aplicada às correções de ponto."""
        entry = open_shift(worker=worker)
        corrigido = correct_entry(
            entry=entry,
            user=manager,
            reason="esqueceu-se de marcar a saída",
            check_out=entry.check_in + datetime.timedelta(hours=8),
        )
        assert corrigido.corrected_by == manager
        assert corrigido.corrected_at is not None
        assert corrigido.correction_reason == "esqueceu-se de marcar a saída"

    def test_registo_manual_exige_motivo(self, worker, manager):
        with pytest.raises(ValidationError):
            add_manual_entry(worker=worker, user=manager, reason="", check_in=timezone.now())

    def test_registo_manual_nasce_auditado(self, worker, manager):
        agora = timezone.now()
        entry = add_manual_entry(
            worker=worker,
            user=manager,
            reason="não marcou o dia todo",
            check_in=agora - datetime.timedelta(hours=9),
            check_out=agora - datetime.timedelta(hours=1),
        )
        assert entry.corrected_by == manager
        assert entry.correction_reason


class TestFerias:
    def _pedido(self, worker, inicio, fim, status=VacationRequest.Status.PENDENTE):
        return VacationRequest.objects.create(
            worker=worker,
            start_date=datetime.date.fromisoformat(inicio),
            end_date=datetime.date.fromisoformat(fim),
            status=status,
        )

    def test_decisao_guarda_autor_e_data(self, worker, manager):
        pedido = self._pedido(worker, "2026-10-01", "2026-10-07")
        decidido = decide_request(request_obj=pedido, user=manager, approve=True, note="boas férias")
        assert decidido.status == VacationRequest.Status.APROVADO
        assert decidido.decided_by == manager
        assert decidido.decided_at is not None

    def test_pedido_decidido_nao_se_redecide(self, worker, manager):
        pedido = self._pedido(worker, "2026-10-01", "2026-10-07")
        decide_request(request_obj=pedido, user=manager, approve=False)
        with pytest.raises(ValidationError):
            decide_request(request_obj=pedido, user=manager, approve=True)

    def test_vacation_overlap_flagged(self, worker, outro_worker):
        """Invariante 6: sobreposição com aprovado do mesmo trabalhador."""
        self._pedido(worker, "2026-10-01", "2026-10-10", VacationRequest.Status.APROVADO)
        sobreposto = self._pedido(worker, "2026-10-08", "2026-10-15")
        sem_conflito = self._pedido(worker, "2026-10-11", "2026-10-15")
        de_outro = self._pedido(outro_worker, "2026-10-08", "2026-10-15")
        assert sobreposto.has_overlap
        assert not sem_conflito.has_overlap
        assert not de_outro.has_overlap

    def test_aprovado_nao_se_apaga_no_admin(self, worker, manager):
        """Invariante 6: pedidos aprovados não se apagam."""
        from django.contrib.admin.sites import site

        pedido = self._pedido(worker, "2026-10-01", "2026-10-07", VacationRequest.Status.APROVADO)
        admin_instance = site._registry[VacationRequest]
        assert admin_instance.has_delete_permission(request=None, obj=pedido) is False

    def test_aviso_de_sobreposicao_na_lista(self, client, worker, manager):
        self._pedido(worker, "2026-10-01", "2026-10-10", VacationRequest.Status.APROVADO)
        self._pedido(worker, "2026-10-08", "2026-10-15")
        client.force_login(manager)
        corpo = client.get(reverse("vacations:lista")).content.decode()
        assert "Sobrepõe aprovado" in corpo


class TestPermissoesPessoas:
    def test_staff_cannot_see_others_data(self, client, staff_user, worker):
        """Colaborador não acede a ponto nem férias de terceiros: as vistas
        de equipa do backoffice devolvem 403."""
        entry = open_shift(worker=worker)
        client.force_login(staff_user)
        urls = [
            reverse("workers:lista"),
            reverse("attendance:dia"),
            reverse("attendance:corrigir", args=[entry.pk]),
            reverse("attendance:acrescentar", args=[worker.pk]),
            reverse("vacations:lista"),
            reverse("vacations:novo"),
        ]
        for url in urls:
            assert client.get(url).status_code == 403, url

    def test_stock_user_nao_gere_pessoas(self, client, stock_user):
        """Matriz da secção 7: responsável de stock não gere trabalhadores."""
        client.force_login(stock_user)
        assert client.get(reverse("workers:lista")).status_code == 403
        assert client.get(reverse("vacations:lista")).status_code == 403

    def test_gerente_acede(self, client, manager):
        client.force_login(manager)
        for name in ["workers:lista", "attendance:dia", "vacations:lista"]:
            assert client.get(reverse(name)).status_code == 200, name


class TestFluxoBackoffice:
    def test_dia_mostra_por_resolver_de_dia_anterior(self, client, worker, manager):
        open_shift(worker=worker, at=timezone.now() - datetime.timedelta(days=1, hours=2))
        client.force_login(manager)
        corpo = client.get(reverse("attendance:dia")).content.decode()
        assert "Por resolver" in corpo

    def test_aceitacao_ponto(self, client, worker, manager):
        """Aceitação (docx): entrada e saída no mesmo dia, consultáveis
        pelo gerente no histórico da equipa."""
        agora = timezone.now()
        open_shift(worker=worker, at=agora - datetime.timedelta(hours=8))
        close_shift(worker=worker, at=agora)
        client.force_login(manager)
        corpo = client.get(reverse("attendance:dia")).content.decode()
        assert worker.full_name in corpo
        assert "em falta" not in corpo

    def test_aceitacao_ferias(self, client, worker, manager):
        """Aceitação (docx): pedido criado, decidido pelo gerente e tudo
        em histórico."""
        client.force_login(manager)
        resp = client.post(
            reverse("vacations:novo"),
            {
                "worker": worker.pk,
                "start_date": "2026-10-01",
                "end_date": "2026-10-07",
                "request_note": "casamento",
            },
        )
        assert resp.status_code == 302
        pedido = VacationRequest.objects.get()
        resp = client.post(
            reverse("vacations:decidir", args=[pedido.pk, "aprovar"]),
            {"decision_note": "aprovado com gosto"},
        )
        assert resp.status_code == 302
        pedido.refresh_from_db()
        assert pedido.status == VacationRequest.Status.APROVADO
        assert pedido.decided_by == manager
        corpo = client.get(reverse("vacations:lista")).content.decode()
        assert "aprovado com gosto" in corpo

    def test_correcao_via_view(self, client, worker, manager):
        entry = open_shift(worker=worker, at=timezone.now() - datetime.timedelta(hours=8))
        client.force_login(manager)
        check_in = timezone.localtime(entry.check_in)
        resp = client.post(
            reverse("attendance:corrigir", args=[entry.pk]),
            {
                "check_in": check_in.strftime("%Y-%m-%dT%H:%M"),
                "check_out": (check_in + datetime.timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M"),
                "reason": "esqueceu a saída",
            },
        )
        assert resp.status_code == 302
        entry.refresh_from_db()
        assert entry.check_out is not None
        assert entry.corrected_by == manager
