"""Fase 7: quiosque do tablet partilhado (nome → código → ação) e app do
colaborador sem botão de ponto. Também o que ficou da Fase 3: histórico,
férias, PWA e dashboard."""
import datetime

import pytest
from django.core import signing
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from accounts.views import DEVICE_COOKIE
from attendance.models import TimeEntry
from attendance.services import open_shift
from core.models import Restaurant, WorkArea
from kiosk import views as kiosk_views
from shifts.models import Shift
from vacations.models import VacationRequest
from workers.models import Worker

from .quiosque import ativar_tablet, escrever_codigo, picar

pytestmark = pytest.mark.django_db

H = datetime.timedelta(hours=1)


@pytest.fixture
def marta(restaurant, staff_user):
    w = Worker.objects.create(restaurant=restaurant, full_name="Marta Silva", job_title="sala", user=staff_user)
    w.set_kiosk_code("2468")
    return w


@pytest.fixture
def rui(restaurant):
    """Sem conta da app: pica no tablet na mesma."""
    w = Worker.objects.create(restaurant=restaurant, full_name="Rui Costa")
    w.set_kiosk_code("1122")
    return w


@pytest.fixture
def tablet(client, manager):
    ativar_tablet(client, manager)
    return client


def _turno_publicado(worker, inicio, horas=4):
    return Shift.objects.create(
        restaurant=worker.restaurant,
        worker=worker,
        start_at=inicio,
        end_at=inicio + horas * H,
        state=Shift.State.PUBLICADO,
    )


class TestQuiosqueAcesso:
    def test_dispositivo_nao_ativado_bloqueia(self, client, marta):
        for url in [reverse("kiosk:inicio"), reverse("kiosk:codigo", args=[marta.pk])]:
            resp = client.get(url)
            assert resp.status_code == 403
            assert "não está ativado" in resp.content.decode()

    def test_lista_so_tem_ativos_com_codigo_do_restaurante(self, tablet, restaurant, marta):
        Worker.objects.create(restaurant=restaurant, full_name="Sem Código")
        inativo = Worker.objects.create(restaurant=restaurant, full_name="Saiu da Casa", is_active=False)
        inativo.set_kiosk_code("9999")
        outra = Restaurant.objects.create(name="Outra Casa", slug="outra-casa")
        alheio = Worker.objects.create(restaurant=outra, full_name="De Outra Casa")
        alheio.set_kiosk_code("9999")
        corpo = tablet.get(reverse("kiosk:inicio")).content.decode()
        assert "Marta Silva" in corpo
        for nome in ["Sem Código", "Saiu da Casa", "De Outra Casa"]:
            assert nome not in corpo
        assert tablet.get(reverse("kiosk:codigo", args=[alheio.pk])).status_code == 404

    def test_cookie_antigo_sem_modo_conta_como_partilhado(self, client, manager, marta):
        client.cookies[DEVICE_COOKIE] = signing.dumps({"por": manager.pk}, salt=DEVICE_COOKIE)
        resp = client.get(reverse("kiosk:inicio"))
        assert resp.status_code == 200
        assert "Marta Silva" in resp.content.decode()

    def test_cookie_antigo_de_telemovel_pessoal_nao_abre_o_quiosque(self, client, manager, marta):
        client.cookies[DEVICE_COOKIE] = signing.dumps({"por": manager.pk, "partilhado": False}, salt=DEVICE_COOKIE)
        assert client.get(reverse("kiosk:inicio")).status_code == 403

    def test_pagina_do_dispositivo_sem_modo_pessoal(self, client, manager):
        client.force_login(manager)
        client.post(reverse("accounts:dispositivo"))
        corpo = client.get(reverse("accounts:dispositivo")).content.decode()
        assert "Ativado" in corpo and "/quiosque/" in corpo
        assert "Uma só pessoa" not in corpo


class TestQuiosqueCodigo:
    def test_codigo_errado(self, tablet, marta):
        resp = escrever_codigo(tablet, marta, "0000")
        assert "Código errado" in resp.content.decode()
        assert "token" not in resp.context

    def test_bloqueio_ao_fim_de_cinco_falhas(self, tablet, marta):
        for _ in range(5):
            escrever_codigo(tablet, marta, "0000")
        resp = escrever_codigo(tablet, marta)
        assert "Demasiadas tentativas" in resp.content.decode()

    def test_codigo_certo_mostra_so_as_acoes_do_estado(self, tablet, marta):
        corpo = escrever_codigo(tablet, marta).content.decode()
        assert "Fora de turno" in corpo
        assert 'value="entrada"' in corpo and 'value="saida"' not in corpo

        picar(tablet, marta, "entrada")
        corpo = escrever_codigo(tablet, marta).content.decode()
        assert "Em turno desde" in corpo
        assert 'value="saida"' in corpo and 'value="entrada"' not in corpo
        assert "Pausa · Refeição" in corpo and "Pausa · Pausa curta" in corpo


class TestQuiosqueMarcacao:
    def test_entrada_fica_com_origem_e_area_do_tablet(self, client, manager, restaurant, marta):
        cozinha = WorkArea.objects.get(restaurant=restaurant, name="Cozinha")
        ativar_tablet(client, manager, area=cozinha)
        picar(client, marta, "entrada")
        entry = TimeEntry.objects.get(worker=marta)
        assert entry.source == TimeEntry.Source.QUIOSQUE
        assert entry.work_area == cozinha

    def test_kiosk_code_never_opens_a_session(self, tablet, restaurant, manager):
        """Secção 7: depois de picar com código, quem está no tablet
        continua anónimo, mesmo que o titular seja gerente."""
        gerente = Worker.objects.create(restaurant=restaurant, full_name="Gerente Chefe", user=manager)
        gerente.set_kiosk_code("1357")
        resp = picar(tablet, gerente, "entrada", codigo="1357")
        assert "Entrada às" in resp.content.decode()
        assert gerente.open_entry is not None
        assert "_auth_user_id" not in tablet.session
        for url in [reverse("dashboard:home"), reverse("staff:home")]:
            resp = tablet.get(url)
            assert resp.status_code == 302 and reverse("accounts:login") in resp.url

    def test_next_person_does_not_inherit_previous(self, tablet, marta, rui):
        resp = escrever_codigo(tablet, marta)
        token_da_marta = resp.context["token"]
        tablet.post(reverse("kiosk:marcar", args=[marta.pk]), {"token": token_da_marta, "acao": "entrada"})
        # O seguinte não consegue picar em nome dele com o token da Marta,
        # nem com o token da Marta noutra pessoa.
        resp = tablet.post(reverse("kiosk:marcar", args=[rui.pk]), {"token": token_da_marta, "acao": "entrada"})
        assert "Não registado" in resp.content.decode()
        assert rui.open_entry is None
        # Com o próprio código, pica normalmente.
        picar(tablet, rui, "entrada", codigo="1122")
        assert rui.open_entry is not None

    def test_action_token_expires(self, tablet, marta, monkeypatch):
        token = escrever_codigo(tablet, marta).context["token"]
        monkeypatch.setattr(kiosk_views, "TOKEN_MAX_AGE", -1)
        resp = tablet.post(reverse("kiosk:marcar", args=[marta.pk]), {"token": token, "acao": "entrada"})
        assert "O tempo para picar acabou" in resp.content.decode()
        assert not TimeEntry.objects.exists()

    def test_token_forjado_recusado(self, tablet, marta):
        resp = tablet.post(reverse("kiosk:marcar", args=[marta.pk]), {"token": "falso", "acao": "entrada"})
        assert "Não registado" in resp.content.decode()
        assert not TimeEntry.objects.exists()

    def test_token_so_vale_uma_vez(self, tablet, marta):
        token = escrever_codigo(tablet, marta).context["token"]
        url = reverse("kiosk:marcar", args=[marta.pk])
        tablet.post(url, {"token": token, "acao": "entrada"})
        resp = tablet.post(url, {"token": token, "acao": "saida"})
        assert "já foi feita" in resp.content.decode()
        assert marta.open_entry is not None

    def test_pausa_e_fim_de_pausa(self, tablet, restaurant, marta):
        from attendance.models import Break, BreakType

        refeicao = BreakType.objects.get(restaurant=restaurant, name="Refeição")
        picar(tablet, marta, "entrada")
        resp = picar(tablet, marta, "pausa", tipo_pausa=refeicao.pk)
        assert "Início de pausa · Refeição às" in resp.content.decode()
        corpo = escrever_codigo(tablet, marta).content.decode()
        assert 'value="fim_pausa"' in corpo and 'value="saida"' not in corpo
        picar(tablet, marta, "fim_pausa")
        assert Break.objects.get().end is not None

    def test_pausa_de_outro_restaurante_recusada(self, tablet, marta):
        from attendance.models import Break, BreakType

        outra = Restaurant.objects.create(name="Outra Casa", slug="outra-casa")
        alheio = BreakType.objects.filter(restaurant=outra).first()
        picar(tablet, marta, "entrada")
        resp = picar(tablet, marta, "pausa", tipo_pausa=alheio.pk)
        assert "Escolha o tipo de pausa" in resp.content.decode()
        assert not Break.objects.exists()

    def test_erro_do_servico_aparece_como_nao_registado(self, tablet, marta):
        resp = picar(tablet, marta, "saida")
        corpo = resp.content.decode()
        assert "Não registado" in corpo and "não tem turno aberto" in corpo


class TestQuiosqueConfirmacao:
    def test_entry_confirmation_shows_planned_exit_and_forgotten_exit(self, tablet, marta):
        # 30 horas: o dia de trabalho é sempre o anterior, e o turno de hoje não lhe estende o limite.
        antiga = open_shift(worker=marta, at=timezone.now() - 30 * H)
        turno = _turno_publicado(marta, timezone.now())
        resp = picar(tablet, marta, "entrada")
        corpo = resp.content.decode()
        assert f"Saída prevista às {timezone.localtime(turno.end_at):%H:%M}" in corpo
        assert "A saída anterior ficou por picar" in corpo
        assert f"{timezone.localtime(antiga.check_in):%d/%m às %H:%M}" in corpo
        assert "Peça a correção na app" in corpo
        assert resp.context["espera"] == kiosk_views.ESPERA_ENTRADA == 15

    def test_entrada_sem_turno_previsto(self, tablet, marta):
        corpo = picar(tablet, marta, "entrada").content.decode()
        assert "Sem turno previsto hoje" in corpo
        assert "por picar" not in corpo and "por resolver" not in corpo

    def test_entrada_conta_os_registos_por_resolver(self, tablet, marta):
        esquecida = open_shift(worker=marta, at=timezone.now() - 30 * H)
        esquecida.missing_exit = True
        esquecida.save()
        corpo = picar(tablet, marta, "entrada").content.decode()
        assert "Tem <span" in corpo and "1</span> registo por resolver" in corpo
        assert "A saída anterior" not in corpo

    def test_quem_nao_tem_app_fala_com_o_gerente(self, tablet, rui):
        open_shift(worker=rui, at=timezone.now() - 30 * H)
        corpo = picar(tablet, rui, "entrada", codigo="1122").content.decode()
        assert "Fale com o gerente" in corpo and "na app" not in corpo

    def test_saida_tem_confirmacao_minima(self, tablet, marta):
        _turno_publicado(marta, timezone.now())
        picar(tablet, marta, "entrada")
        resp = picar(tablet, marta, "saida")
        corpo = resp.content.decode()
        assert "Saída às" in corpo
        assert "Saída prevista" not in corpo
        assert resp.context["espera"] == kiosk_views.ESPERA_CURTA == 5

    def test_aviso_de_saida_esquecida_no_ecra_de_acoes(self, tablet, marta):
        open_shift(worker=marta, at=timezone.now() - 11 * H)
        corpo = escrever_codigo(tablet, marta).content.decode()
        assert "Já passou da hora prevista de saída" in corpo

    def test_turno_em_curso_sem_aviso(self, tablet, marta):
        _turno_publicado(marta, timezone.now() - 2 * H, horas=8)
        open_shift(worker=marta, at=timezone.now() - 2 * H)
        corpo = escrever_codigo(tablet, marta).content.decode()
        assert "Já passou da hora prevista" not in corpo


class TestAppColaborador:
    def test_home_sem_ficha(self, client, staff_user):
        client.force_login(staff_user)
        resp = client.get(reverse("staff:home"))
        assert resp.status_code == 200
        assert "Falta a ficha de trabalhador" in resp.content.decode()

    def test_staff_app_has_no_mark_button(self, client, marta, staff_user):
        client.force_login(staff_user)
        corpo = client.get(reverse("staff:home")).content.decode()
        assert 'name="acao"' not in corpo
        assert "O ponto pica-se no tablet" in corpo
        with pytest.raises(NoReverseMatch):
            reverse("staff:marcar")
        assert client.post("/equipa/marcar/", {"acao": "entrada"}).status_code == 404
        assert not TimeEntry.objects.exists()

    def test_home_mostra_o_estado_e_o_turno_de_hoje(self, client, marta, staff_user):
        turno = _turno_publicado(marta, timezone.now())
        open_shift(worker=marta, at=timezone.now())
        client.force_login(staff_user)
        corpo = client.get(reverse("staff:home")).content.decode()
        assert "Em turno" in corpo
        assert f"{timezone.localtime(turno.start_at):%H:%M}" in corpo

    def test_home_sem_turno_publicado(self, client, marta, staff_user):
        client.force_login(staff_user)
        corpo = client.get(reverse("staff:home")).content.decode()
        assert "Fora de turno" in corpo and "Sem turno publicado para hoje" in corpo

    def test_totais_do_dia(self, client, marta, staff_user):
        open_shift(worker=marta, at=timezone.now() - datetime.timedelta(hours=3, minutes=10))
        client.force_login(staff_user)
        corpo = client.get(reverse("staff:home")).content.decode()
        assert "3h1" in corpo  # 3h10 ou 3h11 conforme o segundo

    def test_equipa_sem_sessao_vai_para_o_login(self, client):
        for nome in ["staff:home", "staff:historico", "staff:ferias", "staff:turnos"]:
            resp = client.get(reverse(nome))
            assert resp.status_code == 302
            assert reverse("accounts:login") in resp.url, nome

    def test_pin_login_ja_nao_existe(self, client):
        assert client.get("/equipa/entrar/").status_code == 404


class TestHistoricoEFerias:
    def test_historico_proprio(self, client, marta, staff_user):
        open_shift(worker=marta)
        client.force_login(staff_user)
        corpo = client.get(reverse("staff:historico")).content.decode()
        assert "em turno" in corpo

    def test_pedido_de_ferias_em_tres_campos(self, client, marta, staff_user):
        client.force_login(staff_user)
        resp = client.post(
            reverse("staff:ferias"),
            {"start_date": "2026-10-01", "end_date": "2026-10-07", "request_note": "casamento"},
        )
        assert resp.status_code == 302
        pedido = VacationRequest.objects.get()
        assert pedido.worker == marta
        assert pedido.status == VacationRequest.Status.PENDENTE

    def test_lista_so_mostra_os_proprios_pedidos(self, client, restaurant, marta, staff_user):
        outro = Worker.objects.create(restaurant=restaurant, full_name="Rui Gomes")
        VacationRequest.objects.create(
            worker=outro,
            start_date=datetime.date(2026, 10, 1),
            end_date=datetime.date(2026, 10, 7),
            request_note="segredo do rui",
        )
        client.force_login(staff_user)
        corpo = client.get(reverse("staff:ferias")).content.decode()
        assert "segredo do rui" not in corpo


class TestPWA:
    def test_sw_servido_na_raiz(self, client):
        resp = client.get("/sw.js")
        assert resp.status_code == 200
        assert "javascript" in resp["Content-Type"]
        assert "opero-shell" in resp.content.decode()

    def test_manifest_disponivel(self, client, settings):
        import pathlib

        manifest = pathlib.Path(settings.BASE_DIR) / "static" / "manifest.webmanifest"
        assert manifest.exists()
        conteudo = manifest.read_text(encoding="utf-8")
        assert '"start_url": "/equipa/"' in conteudo

    def test_app_js_sem_fila_offline(self, settings):
        import pathlib

        conteudo = (pathlib.Path(settings.BASE_DIR) / "static" / "js" / "app.js").read_text(encoding="utf-8")
        assert "serviceWorker" in conteudo
        assert "localStorage" not in conteudo and "marcado_em" not in conteudo


class TestDashboard:
    def test_dashboard_mostra_os_quatro_sinais(self, client, restaurant, manager):
        import datetime as dt

        from attendance.services import open_shift as abrir
        from inventory.models import Category, Item

        cat = Category.objects.create(restaurant=restaurant, name="Cat dash")
        Item.objects.create(restaurant=restaurant, name="Artigo vazio", category=cat, minimum_stock=1)
        w = Worker.objects.create(restaurant=restaurant, full_name="Bea Nunes")
        abrir(worker=w, at=timezone.now() - dt.timedelta(hours=2))
        VacationRequest.objects.create(
            worker=w,
            start_date=dt.date.today() + dt.timedelta(days=10),
            end_date=dt.date.today() + dt.timedelta(days=12),
        )
        client.force_login(manager)
        corpo = client.get(reverse("dashboard:home")).content.decode()
        assert "Artigo vazio" in corpo
        assert "Bea Nunes" in corpo
        assert "Em turno agora" in corpo

    def test_dashboard_do_resp_stock_sem_areas_de_pessoas(self, client, restaurant, stock_user):
        client.force_login(stock_user)
        corpo = client.get(reverse("dashboard:home")).content.decode()
        assert "Stock abaixo" in corpo
        assert "Em turno agora" not in corpo

    def test_comando_demo_e_idempotente(self, db):
        from django.core.management import call_command

        call_command("demo", verbosity=0)
        call_command("demo", verbosity=0)
        from core.models import Restaurant

        assert Restaurant.objects.filter(slug="tasca-da-esquina").count() == 1
        assert Worker.objects.filter(full_name="Marta Silva").count() == 1
        gustavo = Worker.objects.get(full_name="Gustavo Reis")
        assert gustavo.user.role == gustavo.user.Role.MANAGER
        assert gustavo.check_kiosk_code("1357")
