"""Fase 5, primeiro bloco: dia de trabalho, áreas, origem, pausas e
histórico de correções."""
import datetime
import zoneinfo

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from attendance.models import Break, BreakType, EntryCorrection, TimeEntry
from attendance.services import (
    add_manual_entry,
    close_shift,
    correct_entry,
    end_break,
    open_shift,
    start_break,
)
from core.models import WorkArea
from workers.models import Worker

from .quiosque import ativar_tablet, escrever_codigo, picar

pytestmark = pytest.mark.django_db

LISBOA = zoneinfo.ZoneInfo("Europe/Lisbon")


def _local(*args):
    return datetime.datetime(*args, tzinfo=LISBOA)


@pytest.fixture
def worker(restaurant, staff_user):
    w = Worker.objects.create(restaurant=restaurant, full_name="Marta Silva", user=staff_user)
    w.set_kiosk_code("2468")
    return w


@pytest.fixture
def refeicao(restaurant):
    return BreakType.objects.get(restaurant=restaurant, name="Refeição")


@pytest.fixture
def pausa_curta(restaurant):
    return BreakType.objects.get(restaurant=restaurant, name="Pausa curta")


class TestSementes:
    def test_restaurante_novo_tem_areas_e_tipos_de_pausa(self, restaurant):
        assert set(WorkArea.objects.filter(restaurant=restaurant).values_list("name", flat=True)) == {
            "Cozinha",
            "Sala",
            "Bar",
        }
        assert dict(BreakType.objects.filter(restaurant=restaurant).values_list("name", "paid")) == {
            "Refeição": False,
            "Pausa curta": True,
        }


class TestDiaDeTrabalho:
    def test_overnight_shift_counts_on_work_date(self, client, worker, manager):
        """Um turno das 19h às 2h conta todo no dia da entrada, nas duas
        superfícies."""
        open_shift(worker=worker, at=_local(2026, 10, 20, 19, 0))
        entry = close_shift(worker=worker, at=_local(2026, 10, 21, 2, 0))
        assert entry.work_date == datetime.date(2026, 10, 20)

        client.force_login(manager)
        dia_20 = client.get(reverse("attendance:dia") + "?dia=2026-10-20").content.decode()
        dia_21 = client.get(reverse("attendance:dia") + "?dia=2026-10-21").content.decode()
        assert "19:00" in dia_20 and "7h00" in dia_20
        assert "19:00" not in dia_21

    def test_work_date_na_hora_local_e_nao_em_utc(self, worker):
        # 00:30 em Lisboa no verão são 23:30 UTC do dia anterior.
        entry = open_shift(worker=worker, at=_local(2026, 7, 15, 0, 30))
        assert entry.work_date == datetime.date(2026, 7, 15)

    def test_work_date_across_dst_change(self, worker):
        """Na noite da mudança de hora (25 de outubro de 2026, 2h → 1h),
        um turno das 22h às 6h conta no dia da entrada e dura 9 horas."""
        open_shift(worker=worker, at=_local(2026, 10, 24, 22, 0))
        entry = close_shift(worker=worker, at=_local(2026, 10, 25, 6, 0))
        assert entry.work_date == datetime.date(2026, 10, 24)
        assert entry.worked() == datetime.timedelta(hours=9)

    def test_correcao_da_entrada_atualiza_o_dia(self, worker, manager):
        entry = open_shift(worker=worker, at=_local(2026, 10, 20, 9, 0))
        close_shift(worker=worker, at=_local(2026, 10, 20, 17, 0))
        correct_entry(
            entry=entry, user=manager, reason="marcou no dia errado",
            check_in=_local(2026, 10, 19, 9, 0), check_out=_local(2026, 10, 19, 17, 0),
        )
        entry.refresh_from_db()
        assert entry.work_date == datetime.date(2026, 10, 19)


class TestAreaEOrigem:
    def test_marcacao_herda_area_do_tablet(self, client, manager, worker, restaurant):
        cozinha = WorkArea.objects.get(restaurant=restaurant, name="Cozinha")
        ativar_tablet(client, manager, area=cozinha)
        picar(client, worker, "entrada")
        entry = TimeEntry.objects.get(worker=worker)
        assert entry.work_area == cozinha
        assert entry.source == TimeEntry.Source.QUIOSQUE

    def test_tablet_sem_area(self, client, manager, worker):
        ativar_tablet(client, manager)
        picar(client, worker, "entrada")
        assert TimeEntry.objects.get(worker=worker).work_area is None

    def test_area_arquivada_nao_e_herdada(self, client, manager, worker, restaurant):
        bar = WorkArea.objects.get(restaurant=restaurant, name="Bar")
        ativar_tablet(client, manager, area=bar)
        bar.archived_at = timezone.now()
        bar.save()
        picar(client, worker, "entrada")
        assert TimeEntry.objects.get(worker=worker).work_area is None

    def test_registo_manual_tem_origem_gerente(self, worker, manager):
        entry = add_manual_entry(
            worker=worker, user=manager, reason="dia sem marcação",
            check_in=_local(2026, 10, 20, 9, 0), check_out=_local(2026, 10, 20, 17, 0),
        )
        assert entry.source == TimeEntry.Source.GERENTE


class TestPausas:
    def test_break_requires_open_entry(self, worker, refeicao):
        with pytest.raises(ValidationError, match="Marque primeiro a entrada"):
            start_break(worker=worker, break_type=refeicao)

    def test_so_uma_pausa_aberta(self, worker, refeicao, pausa_curta):
        open_shift(worker=worker, at=timezone.now() - datetime.timedelta(hours=2))
        start_break(worker=worker, break_type=refeicao)
        with pytest.raises(ValidationError, match="Já está em pausa"):
            start_break(worker=worker, break_type=pausa_curta)

    def test_constraint_de_pausa_aberta_na_bd(self, worker, refeicao):
        entry = open_shift(worker=worker, at=timezone.now() - datetime.timedelta(hours=2))
        Break.objects.create(entry=entry, break_type=refeicao, start=timezone.now() - datetime.timedelta(hours=1))
        with pytest.raises(IntegrityError), transaction.atomic():
            Break.objects.create(entry=entry, break_type=refeicao, start=timezone.now())

    def test_terminar_pausa_sem_pausa(self, worker):
        open_shift(worker=worker, at=timezone.now() - datetime.timedelta(hours=1))
        with pytest.raises(ValidationError, match="Não está em pausa"):
            end_break(worker=worker)

    def test_tipo_arquivado_recusado(self, worker, refeicao):
        open_shift(worker=worker, at=timezone.now() - datetime.timedelta(hours=1))
        refeicao.archived_at = timezone.now()
        refeicao.save()
        with pytest.raises(ValidationError, match="já não está em uso"):
            start_break(worker=worker, break_type=refeicao)

    def test_unpaid_break_excluded_from_total(self, worker, refeicao, pausa_curta):
        open_shift(worker=worker, at=_local(2026, 10, 20, 9, 0))
        start_break(worker=worker, break_type=refeicao, at=_local(2026, 10, 20, 13, 0))
        end_break(worker=worker, at=_local(2026, 10, 20, 14, 0))
        start_break(worker=worker, break_type=pausa_curta, at=_local(2026, 10, 20, 16, 0))
        end_break(worker=worker, at=_local(2026, 10, 20, 16, 15))
        entry = close_shift(worker=worker, at=_local(2026, 10, 20, 18, 0))
        # 9 horas de turno, menos 1 hora de refeição; a pausa curta é paga.
        assert entry.worked() == datetime.timedelta(hours=8)

    def test_saida_fecha_pausa_aberta(self, worker, refeicao):
        open_shift(worker=worker, at=_local(2026, 10, 20, 9, 0))
        start_break(worker=worker, break_type=refeicao, at=_local(2026, 10, 20, 13, 0))
        entry = close_shift(worker=worker, at=_local(2026, 10, 20, 14, 0))
        pausa = entry.breaks.get()
        assert pausa.end == _local(2026, 10, 20, 14, 0)
        assert entry.worked() == datetime.timedelta(hours=4)

    def test_tres_estados_no_quiosque(self, client, manager, worker, refeicao):
        ativar_tablet(client, manager)
        html = escrever_codigo(client, worker).content.decode()
        assert 'value="entrada"' in html and 'value="pausa"' not in html

        picar(client, worker, "entrada")
        html = escrever_codigo(client, worker).content.decode()
        assert 'value="saida"' in html and 'value="pausa"' in html
        assert "Pausa · Refeição" in html

        html = picar(client, worker, "pausa", tipo_pausa=refeicao.pk).content.decode()
        assert "Início de pausa · Refeição às" in html
        html = escrever_codigo(client, worker).content.decode()
        assert 'value="fim_pausa"' in html and "Terminar pausa" in html
        assert 'value="saida"' not in html

        html = picar(client, worker, "fim_pausa").content.decode()
        assert "Fim de pausa às" in html
        assert 'value="saida"' in escrever_codigo(client, worker).content.decode()
        assert Break.objects.get().end is not None

    def test_um_so_tipo_de_pausa_diz_iniciar_pausa(self, client, manager, worker, pausa_curta):
        pausa_curta.archived_at = timezone.now()
        pausa_curta.save()
        ativar_tablet(client, manager)
        picar(client, worker, "entrada")
        html = escrever_codigo(client, worker).content.decode()
        assert "Iniciar pausa" in html and "Pausa · " not in html

    def test_tipo_de_pausa_arquivado_recusado(self, client, manager, worker, pausa_curta):
        ativar_tablet(client, manager)
        picar(client, worker, "entrada")
        pausa_curta.archived_at = timezone.now()
        pausa_curta.save()
        html = picar(client, worker, "pausa", tipo_pausa=pausa_curta.pk).content.decode()
        assert "Escolha o tipo de pausa" in html
        assert not Break.objects.exists()

    def test_totais_staff_descontam_pausa_nao_paga(self, client, manager, worker, refeicao):
        inicio = timezone.now() - datetime.timedelta(hours=3)
        open_shift(worker=worker, at=inicio)
        start_break(worker=worker, break_type=refeicao, at=inicio + datetime.timedelta(minutes=30))
        end_break(worker=worker, at=inicio + datetime.timedelta(minutes=90))
        close_shift(worker=worker, at=inicio + datetime.timedelta(hours=2))
        client.force_login(worker.user)
        html = client.get(reverse("staff:home")).content.decode()
        assert "1h00" in html


class TestHistoricoDeCorrecoes:
    def test_correction_keeps_previous_values(self, worker, manager):
        """Invariante 7: uma correção guarda o antes e o depois."""
        entry = open_shift(worker=worker, at=_local(2026, 10, 20, 9, 0))
        close_shift(worker=worker, at=_local(2026, 10, 20, 17, 0))
        correct_entry(entry=entry, user=manager, reason="entrou às 8h", check_in=_local(2026, 10, 20, 8, 0))
        correct_entry(entry=entry, user=manager, reason="saiu às 18h", check_out=_local(2026, 10, 20, 18, 0))

        primeira, segunda = entry.corrections.order_by("pk")
        assert primeira.old_check_in == _local(2026, 10, 20, 9, 0)
        assert primeira.new_check_in == _local(2026, 10, 20, 8, 0)
        assert primeira.old_check_out == primeira.new_check_out == _local(2026, 10, 20, 17, 0)
        assert segunda.old_check_out == _local(2026, 10, 20, 17, 0)
        assert segunda.new_check_out == _local(2026, 10, 20, 18, 0)
        assert segunda.corrected_by == manager and segunda.reason == "saiu às 18h"

        entry.refresh_from_db()
        assert entry.correction_reason == "saiu às 18h"
        assert entry.corrected_by == manager

    def test_correcao_recusada_nao_deixa_historico(self, worker, manager):
        entry = open_shift(worker=worker, at=_local(2026, 10, 20, 9, 0))
        close_shift(worker=worker, at=_local(2026, 10, 20, 17, 0))
        with pytest.raises(ValidationError):
            correct_entry(entry=entry, user=manager, reason="x", check_out=_local(2026, 10, 20, 8, 0))
        assert not EntryCorrection.objects.exists()

    def test_registo_manual_deixa_linha_criar(self, worker, manager):
        entry = add_manual_entry(
            worker=worker, user=manager, reason="dia sem marcação",
            check_in=_local(2026, 10, 20, 9, 0), check_out=_local(2026, 10, 20, 17, 0),
        )
        linha = entry.corrections.get()
        assert linha.kind == EntryCorrection.Kind.CRIAR
        assert linha.old_check_in is None and linha.new_check_in == _local(2026, 10, 20, 9, 0)

    def test_historico_em_taloes_na_pagina_de_correcao(self, client, worker, manager):
        entry = open_shift(worker=worker, at=_local(2026, 10, 20, 9, 0))
        close_shift(worker=worker, at=_local(2026, 10, 20, 17, 0))
        correct_entry(entry=entry, user=manager, reason="entrou às 8h", check_in=_local(2026, 10, 20, 8, 0))
        client.force_login(manager)
        html = client.get(reverse("attendance:corrigir", args=[entry.pk])).content.decode()
        assert "Histórico de correções" in html
        assert "antes 20/10 09:00" in html and "depois 20/10 08:00" in html
        assert "entrou às 8h" in html

    def test_historico_nao_se_apaga_no_admin(self, client, worker, admin_user):
        from django.contrib import admin

        from attendance.admin import EntryCorrectionAdmin

        modelo_admin = EntryCorrectionAdmin(EntryCorrection, admin.site)
        assert not modelo_admin.has_delete_permission(None)
        assert not modelo_admin.has_change_permission(None)
