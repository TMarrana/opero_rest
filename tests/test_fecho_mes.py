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
    annul_entry,
    close_shift,
    correct_entry,
    decide_correction,
    end_break,
    open_shift,
    request_correction,
    start_break,
)
from core.utils import nome_do_mes
from workers.models import Worker

pytestmark = pytest.mark.django_db

LISBOA = zoneinfo.ZoneInfo("Europe/Lisbon")
H = datetime.timedelta(hours=1)


def _local(*args):
    return datetime.datetime(*args, tzinfo=LISBOA)


@pytest.fixture
def worker(restaurant, staff_user):
    w = Worker.objects.create(restaurant=restaurant, full_name="Marta Silva", user=staff_user)
    w.set_kiosk_code("2468")
    return w


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

    def test_de_madrugada_quem_esta_em_turno_impede_a_aprovacao(self, worker, manager, mes_passado):
        """Dia 1 à 1h: quem entrou às 20h do último dia do mês ainda não picou
        a saída. Aprovar fechava o mês, e o tablet recusava-lhe depois a saída."""
        fim = mes.month_range(mes_passado)[1]
        open_shift(worker=worker, at=_local(fim.year, fim.month, fim.day, 20))
        dia1 = mes.next_month(mes_passado)
        agora = _local(dia1.year, dia1.month, 1, 1)
        with pytest.raises(ValidationError, match="ainda está em turno"):
            mes.approve_month(worker=worker, month=mes_passado, user=manager, now=agora)
        assert mes.pending_items(worker, mes_passado, now=agora) == {"por_resolver": 0, "em_turno": 1, "pedidos": 0}

    def test_fecho_mostra_quem_ainda_esta_em_turno(self, client, worker, manager):
        entrada = open_shift(worker=worker, at=timezone.now() - H)
        client.force_login(manager)
        html = client.get(reverse("attendance:mes") + f"?mes={entrada.work_date:%Y-%m}").content.decode()
        assert "Ainda em turno" in html

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
        assert f"O mês de <span class=\"font-dados\">{nome_do_mes(mes_passado)} de {mes_passado.year}</span> está por fechar" in html
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


class TestDetalheDoMes:
    """Pop-up com as horas dia a dia, e correções que voltam ao fecho com
    as horas novas."""

    def test_detalhe_mostra_os_dias(self, client, worker, manager, mes_passado):
        open_shift(worker=worker, at=_dia(mes_passado, 3))
        close_shift(worker=worker, at=_dia(mes_passado, 3, 17))
        open_shift(worker=worker, at=_dia(mes_passado, 8, 10))
        close_shift(worker=worker, at=_dia(mes_passado, 8, 14))
        client.force_login(manager)
        html = client.get(reverse("attendance:mes") + f"?mes={mes_passado:%Y-%m}").content.decode()
        assert f'x-on:click="detalhe = {worker.pk}"' in html
        assert f"03/{mes_passado:%m}" in html and f"08/{mes_passado:%m}" in html
        assert "em 2 dias" in html
        assert "12h00" in html  # 8h + 4h

    def test_correcao_volta_ao_fecho_com_as_horas_novas(self, client, worker, manager, mes_passado):
        open_shift(worker=worker, at=_dia(mes_passado, 4, 9))
        entry = close_shift(worker=worker, at=_dia(mes_passado, 4, 17))
        client.force_login(manager)
        url_mes = reverse("attendance:mes") + f"?mes={mes_passado:%Y-%m}"
        resp = client.get(url_mes)
        assert "8h00" in resp.content.decode()
        assert "no-store" in resp["Cache-Control"]
        resp = client.post(
            reverse("attendance:corrigir", args=[entry.pk]),
            {
                "check_in": _dia(mes_passado, 4, 9).strftime("%Y-%m-%dT%H:%M"),
                "check_out": _dia(mes_passado, 4, 13).strftime("%Y-%m-%dT%H:%M"),
                "reason": "",
                "voltar": url_mes,
            },
        )
        assert resp.status_code == 302 and resp["Location"] == url_mes
        html = client.get(url_mes).content.decode()
        assert "4h00" in html and "8h00" not in html

    def test_voltar_para_fora_do_site_e_ignorado(self, client, worker, manager, mes_passado):
        open_shift(worker=worker, at=_dia(mes_passado, 4, 9))
        entry = close_shift(worker=worker, at=_dia(mes_passado, 4, 17))
        client.force_login(manager)
        resp = client.post(
            reverse("attendance:corrigir", args=[entry.pk]),
            {
                "check_in": _dia(mes_passado, 4, 9).strftime("%Y-%m-%dT%H:%M"),
                "check_out": _dia(mes_passado, 4, 12).strftime("%Y-%m-%dT%H:%M"),
                "voltar": "https://exemplo.com/",
            },
        )
        assert resp["Location"].startswith(reverse("attendance:dia"))

    def test_acrescentar_sem_motivo_pela_vista(self, client, worker, manager, mes_passado):
        client.force_login(manager)
        url_mes = reverse("attendance:mes") + f"?mes={mes_passado:%Y-%m}"
        resp = client.post(
            reverse("attendance:acrescentar", args=[worker.pk]),
            {
                "check_in": _dia(mes_passado, 6, 9).strftime("%Y-%m-%dT%H:%M"),
                "check_out": _dia(mes_passado, 6, 15).strftime("%Y-%m-%dT%H:%M"),
                "reason": "",
                "voltar": url_mes,
            },
        )
        assert resp.status_code == 302 and resp["Location"] == url_mes
        assert worker.time_entries.get().corrections.get().reason == ""


class TestQuemEntraNoMes:
    def test_quem_saiu_a_meio_do_mes_entra_no_fecho_e_no_csv(self, client, manager, restaurant, mes_passado):
        w = Worker.objects.create(restaurant=restaurant, full_name="Rita Saiu")
        add_manual_entry(worker=w, user=manager, check_in=_dia(mes_passado, 3), check_out=_dia(mes_passado, 3, 17))
        w.is_active, w.end_date = False, _dia(mes_passado, 15).date()
        w.save()
        client.force_login(manager)
        url = reverse("attendance:mes") + f"?mes={mes_passado:%Y-%m}"
        assert "Rita Saiu" in client.get(url).content.decode()
        mes.approve_month(worker=w, month=mes_passado, user=manager)
        assert "Rita Saiu" in client.get(url + "&exportar=csv").content.decode()

    def test_quem_comeca_depois_do_mes_nao_esta_por_aprovar(self, client, manager, restaurant, mes_passado):
        Worker.objects.create(
            restaurant=restaurant, full_name="Jorge Novo", start_date=timezone.localdate().replace(day=1)
        )
        client.force_login(manager)
        url = reverse("attendance:mes") + f"?mes={mes_passado:%Y-%m}"
        assert "Jorge Novo" not in client.get(url).content.decode()
        assert "por fechar" not in client.get(reverse("dashboard:home")).content.decode()

    def test_desativar_guarda_a_data_de_saida(self, client, manager, restaurant):
        w = Worker.objects.create(restaurant=restaurant, full_name="Ana Sai")
        client.force_login(manager)
        client.post(reverse("workers:desativar", args=[w.pk]), {"data_saida": "2026-10-31"})
        w.refresh_from_db()
        assert not w.is_active and w.end_date == datetime.date(2026, 10, 31)

    def test_desativar_sem_data_usa_hoje(self, client, manager, restaurant):
        w = Worker.objects.create(restaurant=restaurant, full_name="Ana Sai")
        client.force_login(manager)
        client.post(reverse("workers:desativar", args=[w.pk]), {"data_saida": ""})
        w.refresh_from_db()
        assert not w.is_active and w.end_date == timezone.localdate()

    def test_data_de_saida_invalida_nao_desativa(self, client, manager, restaurant):
        w = Worker.objects.create(restaurant=restaurant, full_name="Ana Sai")
        client.force_login(manager)
        resp = client.post(reverse("workers:desativar", args=[w.pk]), {"data_saida": "31/02/2026"}, follow=True)
        w.refresh_from_db()
        assert w.is_active and w.end_date is None
        assert "data de saída" in resp.content.decode()

    def test_data_de_saida_no_futuro_nao_desativa(self, client, manager, restaurant):
        """Desativar é já: com uma data futura, a pessoa deixava logo de picar
        nos dias que ainda lhe faltam trabalhar."""
        w = Worker.objects.create(restaurant=restaurant, full_name="Ana Sai")
        client.force_login(manager)
        amanha = timezone.localdate() + datetime.timedelta(days=1)
        resp = client.post(reverse("workers:desativar", args=[w.pk]), {"data_saida": amanha.isoformat()}, follow=True)
        w.refresh_from_db()
        assert w.is_active and w.end_date is None
        assert "A data de saída não pode ser no futuro" in resp.content.decode()

    def test_data_de_saida_antes_do_inicio_nao_desativa(self, client, manager, restaurant):
        w = Worker.objects.create(restaurant=restaurant, full_name="Ana Sai", start_date=datetime.date(2026, 3, 1))
        client.force_login(manager)
        resp = client.post(reverse("workers:desativar", args=[w.pk]), {"data_saida": "2026-02-27"}, follow=True)
        w.refresh_from_db()
        assert w.is_active and w.end_date is None
        assert "não pode ser antes do início" in resp.content.decode()

    def test_seletor_deixa_de_fora_quem_comeca_depois_do_mes(self, restaurant, mes_passado):
        from attendance.selectors import workers_for_month

        depois = mes.next_month(mes_passado)
        Worker.objects.create(restaurant=restaurant, full_name="Novo", start_date=depois)
        assert not workers_for_month(Worker.objects.all(), mes_passado).filter(full_name="Novo").exists()

    def test_seletor_conta_registos_noutra_casa(self, restaurant, manager, mes_passado):
        """Quem saiu antes do mes mas picou noutra casa do grupo nesse mes entra
        no fecho da casa principal."""
        from attendance.selectors import workers_for_month
        from core.models import Restaurant

        outra = Restaurant.objects.create(organization=restaurant.organization, name="Tasca Dois", slug="tasca-dois")
        w = Worker.objects.create(restaurant=restaurant, full_name="Rita Duas", is_active=False,
                                  end_date=mes.previous_month(mes_passado))
        w.other_restaurants.add(outra)
        add_manual_entry(worker=w, user=manager, check_in=_dia(mes_passado, 3), check_out=_dia(mes_passado, 3, 17),
                         restaurant=outra)
        assert w in workers_for_month(Worker.objects.all(), mes_passado)

    def test_ficha_com_historico_pede_a_data_de_saida_ao_desativar(self, client, manager, restaurant, mes_passado):
        w = Worker.objects.create(restaurant=restaurant, full_name="Ana Historico")
        add_manual_entry(worker=w, user=manager, check_in=_dia(mes_passado, 3), check_out=_dia(mes_passado, 3, 17))
        client.force_login(manager)
        html = client.get(reverse("workers:editar", args=[w.pk])).content.decode()
        hoje = f"{timezone.localdate():%Y-%m-%d}"
        assert 'name="data_saida"' in html and f'value="{hoje}"' in html and f'max="{hoje}"' in html
        assert 'form="apagar-trabalhador-form"' in html and 'id="apagar-trabalhador-form"' in html

    def test_reativar_limpa_a_data_de_saida(self, client, manager, restaurant):
        w = Worker.objects.create(
            restaurant=restaurant,
            full_name="Ana Volta",
            job_title="Sala",
            contact="912345678",
            start_date=datetime.date(2025, 1, 2),
            is_active=False,
            end_date=datetime.date(2026, 1, 31),
        )
        client.force_login(manager)
        resp = client.post(
            reverse("workers:editar", args=[w.pk]),
            {
                "full_name": "Ana Volta",
                "job_title": "Sala",
                "contact": "912345678",
                "start_date": "2025-01-02",
                "is_active": "on",
            },
        )
        assert resp.status_code == 302
        w.refresh_from_db()
        assert w.is_active and w.end_date is None

    def test_desativar_pela_caixa_da_ficha_guarda_hoje_como_saida(self, client, manager, restaurant):
        """Tirar o visto de «Trabalhador ativo» é uma saída, como o botão
        Desativar sem data. Sem data de saída, quem não picou nesse mês
        desaparecia do fecho e do CSV."""
        from attendance.selectors import workers_for_month

        w = Worker.objects.create(
            restaurant=restaurant, full_name="Ana Sai", job_title="Sala", contact="912345678",
            start_date=datetime.date(2025, 1, 2),
        )
        client.force_login(manager)
        dados = {"full_name": "Ana Sai", "job_title": "Sala", "contact": "912345678", "start_date": "2025-01-02"}
        assert client.post(reverse("workers:editar", args=[w.pk]), dados).status_code == 302
        w.refresh_from_db()
        assert not w.is_active and w.end_date == timezone.localdate()
        assert w in workers_for_month(Worker.objects.all(), timezone.localdate())

    def test_editar_ficha_ja_inativa_mantem_a_data_de_saida(self, client, manager, restaurant):
        w = Worker.objects.create(
            restaurant=restaurant, full_name="Ana Saiu", job_title="Sala", contact="912345678",
            start_date=datetime.date(2025, 1, 2), is_active=False, end_date=datetime.date(2026, 1, 31),
        )
        client.force_login(manager)
        dados = {"full_name": "Ana Saiu", "job_title": "Sala", "contact": "912345678", "start_date": "2025-01-02",
                 "notes": "Pode voltar no verão"}
        assert client.post(reverse("workers:editar", args=[w.pk]), dados).status_code == 302
        w.refresh_from_db()
        assert not w.is_active and w.end_date == datetime.date(2026, 1, 31)

    def test_seletor_ignora_registos_anulados_e_saidas_anteriores(self, manager, restaurant, mes_passado):
        from attendance.selectors import workers_for_month

        anulado = Worker.objects.create(restaurant=restaurant, full_name="Anulado", is_active=False)
        entrada = add_manual_entry(
            worker=anulado, user=manager, check_in=_dia(mes_passado, 3), check_out=_dia(mes_passado, 3, 17)
        )
        annul_entry(entry=entrada, user=manager, reason="engano")
        com_registo = Worker.objects.create(restaurant=restaurant, full_name="Com registo", is_active=False)
        add_manual_entry(
            worker=com_registo, user=manager, check_in=_dia(mes_passado, 4), check_out=_dia(mes_passado, 4, 17)
        )
        Worker.objects.create(restaurant=restaurant, full_name="Ativo")
        Worker.objects.create(
            restaurant=restaurant,
            full_name="Saiu antes",
            is_active=False,
            end_date=mes_passado - datetime.timedelta(days=1),
        )
        nomes = [w.full_name for w in workers_for_month(Worker.objects.all(), mes_passado)]
        assert nomes == ["Ativo", "Com registo"]
