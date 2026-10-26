"""Fase 8: calendário mensal das ausências no backoffice, com o painel
por célula para marcar, decidir e cancelar, como no planeador de turnos."""
import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from vacations.models import AbsenceType, BlockedPeriod, VacationRequest
from vacations.services import cancel_request, create_request
from workers.models import Worker

pytestmark = pytest.mark.django_db

D = datetime.date
DIA = datetime.timedelta(days=1)


@pytest.fixture
def marta(restaurant, staff_user):
    return Worker.objects.create(restaurant=restaurant, full_name="Marta Silva", user=staff_user)


@pytest.fixture
def rui(restaurant):
    return Worker.objects.create(restaurant=restaurant, full_name="Rui Costa")


@pytest.fixture
def ferias(restaurant):
    return AbsenceType.objects.get(restaurant=restaurant, name="Férias")


def _celula(worker, dia):
    return reverse("vacations:celula", args=[worker.pk, dia.isoformat()])


def _linha(resp, worker):
    return next(linha for linha in resp.context["linhas"] if linha["worker"] == worker)


class TestCalendario:
    def test_mostra_o_mes_com_aprovadas_e_pendentes(self, client, manager, marta, rui, ferias):
        create_request(worker=marta, absence_type=ferias, start_date=D(2026, 11, 9), end_date=D(2026, 11, 11), created_by=manager)
        create_request(worker=rui, absence_type=ferias, start_date=D(2026, 11, 10), end_date=D(2026, 11, 10))
        client.force_login(manager)
        resp = client.get(reverse("vacations:calendario") + "?mes=2026-11")
        assert resp.status_code == 200
        assert len(resp.context["colunas"]) == 30

        celulas = _linha(resp, marta)["celulas"]
        assert [c["dia"].day for c in celulas if c["ausencia"]] == [9, 10, 11]
        assert all(not c["pendente"] and c["texto"] == "Fé" for c in celulas if c["ausencia"])
        rui_10 = _linha(resp, rui)["celulas"][9]
        assert rui_10["ausencia"] is not None and rui_10["pendente"]

        # Só as aprovadas contam como fora.
        assert resp.context["fora"][8:11] == [1, 1, 1]
        corpo = resp.content.decode()
        assert "border-dashed" in corpo
        assert "1</span> pendente" in corpo

    def test_meio_dia_aparece_como_meio(self, client, manager, marta, restaurant):
        tipo = AbsenceType.objects.filter(restaurant=restaurant, half_days=True).first()
        if tipo is None:
            pytest.skip("Sem tipo de origem com meio dia.")
        create_request(worker=marta, absence_type=tipo, start_date=D(2026, 11, 9), end_date=D(2026, 11, 9), half_day=True, created_by=manager)
        client.force_login(manager)
        resp = client.get(reverse("vacations:calendario") + "?mes=2026-11")
        assert _linha(resp, marta)["celulas"][8]["texto"] == "½"

    def test_feriados_fins_de_semana_e_bloqueios_assinalados(self, client, restaurant, manager, marta):
        BlockedPeriod.objects.create(restaurant=restaurant, name="Época de Natal", start=D(2026, 12, 20), end=D(2026, 12, 31))
        client.force_login(manager)
        colunas = client.get(reverse("vacations:calendario") + "?mes=2026-12").context["colunas"]
        natal = colunas[24]
        assert natal["feriado"] == "Natal" and natal["bloqueado"] == "Época de Natal"
        assert colunas[4]["fim_de_semana"]  # sábado, 5 de dezembro
        assert colunas[0]["feriado"] and not colunas[0]["bloqueado"]

    def test_mes_invalido_mostra_o_mes_atual(self, client, manager):
        client.force_login(manager)
        resp = client.get(reverse("vacations:calendario") + "?mes=abc")
        assert resp.context["mes"] == timezone.localdate().replace(day=1)

    def test_navegacao_entre_meses(self, client, manager):
        client.force_login(manager)
        resp = client.get(reverse("vacations:calendario") + "?mes=2026-01")
        assert resp.context["mes_anterior"] == D(2025, 12, 1)
        assert resp.context["mes_seguinte"] == D(2026, 2, 1)

    def test_saldo_por_trabalhador(self, client, manager, marta, ferias):
        create_request(worker=marta, absence_type=ferias, start_date=D(2026, 11, 9), end_date=D(2026, 11, 13), created_by=manager)
        client.force_login(manager)
        resp = client.get(reverse("vacations:calendario") + "?mes=2026-11")
        assert _linha(resp, marta)["saldo"] == 22 - 5

    def test_menu_ferias_abre_o_calendario(self, client, manager):
        client.force_login(manager)
        corpo = client.get(reverse("dashboard:home")).content.decode()
        assert f'href="{reverse("vacations:calendario")}"' in corpo

    def test_so_admin_e_gerente(self, client, staff_user, stock_user, marta):
        for user in [staff_user, stock_user]:
            client.force_login(user)
            assert client.get(reverse("vacations:calendario")).status_code == 403
            assert client.get(_celula(marta, D(2026, 11, 9))).status_code == 403


class TestPainelDaCelula:
    def test_painel_traz_o_dia_e_o_saldo(self, client, manager, marta):
        client.force_login(manager)
        resp = client.get(_celula(marta, D(2026, 11, 9)))
        corpo = resp.content.decode()
        assert "Marta Silva" in corpo and "Marcar ausência" in corpo
        assert 'value="2026-11-09"' in corpo
        assert "dias disponíveis" in corpo

    def test_gerente_marca_ausencia_aprovada(self, client, manager, marta, ferias):
        client.force_login(manager)
        resp = client.post(
            _celula(marta, D(2026, 11, 9)),
            {"acao": "marcar", "absence_type": ferias.pk, "start_date": "2026-11-09", "end_date": "2026-11-13", "request_note": "praia"},
        )
        assert resp.status_code == 302 and resp.url.endswith("?mes=2026-11")
        pedido = VacationRequest.objects.get()
        assert pedido.status == VacationRequest.Status.APROVADO
        assert pedido.decided_by == manager
        assert pedido.days_taken == 5

    def test_datas_trocadas_nao_marcam_nada(self, client, manager, marta, ferias):
        client.force_login(manager)
        resp = client.post(
            _celula(marta, D(2026, 11, 9)),
            {"acao": "marcar", "absence_type": ferias.pk, "start_date": "2026-11-13", "end_date": "2026-11-09"},
            follow=True,
        )
        assert "O fim tem de ser igual ou depois do início" in resp.content.decode()
        assert not VacationRequest.objects.exists()

    def test_aprovar_e_recusar_no_painel(self, client, manager, marta, rui, ferias):
        pedido_marta = create_request(worker=marta, absence_type=ferias, start_date=D(2026, 11, 9), end_date=D(2026, 11, 10))
        pedido_rui = create_request(worker=rui, absence_type=ferias, start_date=D(2026, 11, 9), end_date=D(2026, 11, 10))
        client.force_login(manager)
        assert "Aprovar" in client.get(_celula(marta, D(2026, 11, 9))).content.decode()
        client.post(_celula(marta, D(2026, 11, 9)), {"acao": "aprovar", "pedido": pedido_marta.pk})
        client.post(_celula(rui, D(2026, 11, 9)), {"acao": "recusar", "pedido": pedido_rui.pk, "decision_note": "época alta"})
        pedido_marta.refresh_from_db()
        pedido_rui.refresh_from_db()
        assert pedido_marta.status == VacationRequest.Status.APROVADO and pedido_marta.decided_by == manager
        assert pedido_rui.status == VacationRequest.Status.RECUSADO and pedido_rui.decision_note == "época alta"

    def test_pedido_de_outra_pessoa_nao_se_decide_na_celula_errada(self, client, manager, marta, rui, ferias):
        pedido_rui = create_request(worker=rui, absence_type=ferias, start_date=D(2026, 11, 9), end_date=D(2026, 11, 10))
        client.force_login(manager)
        resp = client.post(_celula(marta, D(2026, 11, 9)), {"acao": "aprovar", "pedido": pedido_rui.pk})
        assert resp.status_code == 404
        pedido_rui.refresh_from_db()
        assert pedido_rui.status == VacationRequest.Status.PENDENTE

    def test_gerente_cancela_ausencia_que_ainda_nao_acabou(self, client, manager, marta, ferias):
        inicio = timezone.localdate() + 10 * DIA
        pedido = create_request(worker=marta, absence_type=ferias, start_date=inicio, end_date=inicio + 4 * DIA, created_by=manager)
        client.force_login(manager)
        assert "Cancelar esta ausência" in client.get(_celula(marta, inicio)).content.decode()
        client.post(_celula(marta, inicio), {"acao": "cancelar", "pedido": pedido.pk})
        pedido.refresh_from_db()
        assert pedido.status == VacationRequest.Status.CANCELADO
        assert pedido.cancelled_by == manager and pedido.cancelled_at is not None
        # Não se apagou nada (invariante 6), e deixa de aparecer no calendário.
        assert VacationRequest.objects.count() == 1
        resp = client.get(reverse("vacations:calendario") + f"?mes={inicio:%Y-%m}")
        assert not any(c["ausencia"] for c in _linha(resp, marta)["celulas"])

    def test_cancelar_volta_o_turno_a_rascunho(self, client, restaurant, manager, marta, ferias):
        from shifts.models import Shift

        inicio = timezone.localdate() + 10 * DIA
        turno = Shift.objects.create(
            restaurant=restaurant,
            worker=marta,
            start_at=timezone.make_aware(datetime.datetime.combine(inicio, datetime.time(11))),
            end_at=timezone.make_aware(datetime.datetime.combine(inicio, datetime.time(16))),
            state=Shift.State.PUBLICADO,
        )
        pedido = create_request(worker=marta, absence_type=ferias, start_date=inicio, end_date=inicio, created_by=manager)
        turno.refresh_from_db()
        assert turno.state == Shift.State.RESERVA
        client.force_login(manager)
        client.post(_celula(marta, inicio), {"acao": "cancelar", "pedido": pedido.pk})
        turno.refresh_from_db()
        assert turno.state == Shift.State.RASCUNHO

    def test_ausencia_que_ja_acabou_nao_se_cancela(self, client, manager, marta, ferias):
        fim = timezone.localdate() - DIA
        pedido = create_request(worker=marta, absence_type=ferias, start_date=fim - 2 * DIA, end_date=fim, created_by=manager)
        client.force_login(manager)
        assert "Cancelar esta ausência" not in client.get(_celula(marta, fim)).content.decode()
        resp = client.post(_celula(marta, fim), {"acao": "cancelar", "pedido": pedido.pk}, follow=True)
        assert "Só se cancelam ausências aprovadas que ainda não acabaram" in resp.content.decode()
        pedido.refresh_from_db()
        assert pedido.status == VacationRequest.Status.APROVADO

    def test_trabalhador_de_outro_restaurante(self, client, manager):
        from core.models import Restaurant

        outra = Restaurant.objects.create(name="Outra Casa", slug="outra-casa")
        alheio = Worker.objects.create(restaurant=outra, full_name="De Outra Casa")
        client.force_login(manager)
        assert client.get(_celula(alheio, D(2026, 11, 9))).status_code == 404


def test_cancelamento_do_colaborador_guarda_quem(marta, ferias):
    inicio = timezone.localdate() + 10 * DIA
    pedido = create_request(worker=marta, absence_type=ferias, start_date=inicio, end_date=inicio)
    cancel_request(request_obj=pedido, worker=marta)
    pedido.refresh_from_db()
    assert pedido.cancelled_by == marta.user
