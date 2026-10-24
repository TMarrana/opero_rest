"""Fase 3: login por PIN, ecrã de ponto do colaborador e fila offline."""
import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from attendance.services import open_shift
from core.mixins import PIN_SESSION_KEY
from vacations.models import VacationRequest
from workers.models import Worker

pytestmark = pytest.mark.django_db


@pytest.fixture
def worker_com_pin(restaurant, staff_user):
    staff_user.set_staff_pin("2468")
    return Worker.objects.create(
        restaurant=restaurant, full_name="Marta Silva", job_title="sala", user=staff_user
    )


def _ativar_dispositivo(client, manager):
    client.force_login(manager)
    client.post(reverse("accounts:dispositivo"))
    client.post(reverse("accounts:logout"))


class TestPinLogin:
    def test_dispositivo_nao_ativado_bloqueia(self, client, worker_com_pin):
        resp = client.get(reverse("staff:pin_login"))
        assert resp.status_code == 403
        assert "não está ativado" in resp.content.decode()

    def test_login_por_pin_em_dispositivo_ativado(self, client, manager, worker_com_pin):
        _ativar_dispositivo(client, manager)
        resp = client.get(reverse("staff:pin_login"))
        assert resp.status_code == 200
        assert "Marta Silva" in resp.content.decode()
        resp = client.post(
            reverse("staff:pin_login"), {"worker": worker_com_pin.pk, "pin": "2468"}
        )
        assert resp.status_code == 302
        assert resp.url == reverse("staff:home")
        assert client.session.get(PIN_SESSION_KEY) is True

    def test_pin_errado_rejeitado(self, client, manager, worker_com_pin):
        _ativar_dispositivo(client, manager)
        resp = client.post(
            reverse("staff:pin_login"), {"worker": worker_com_pin.pk, "pin": "0000"}
        )
        assert resp.status_code == 200
        assert "PIN errado" in resp.content.decode()

    def test_throttling_apos_cinco_falhas(self, client, manager, worker_com_pin):
        _ativar_dispositivo(client, manager)
        for _ in range(5):
            client.post(reverse("staff:pin_login"), {"worker": worker_com_pin.pk, "pin": "0000"})
        resp = client.post(
            reverse("staff:pin_login"), {"worker": worker_com_pin.pk, "pin": "2468"}
        )
        assert "Demasiadas tentativas" in resp.content.decode()

    def test_sessao_pin_real_nao_abre_backoffice(self, client, manager_com_pin_e_worker):
        """A fronteira da secção 7 com um login PIN verdadeiro: o titular
        é gerente, mas a sessão criada por PIN não abre o backoffice."""
        worker, gerente = manager_com_pin_e_worker
        resp = client.post(reverse("staff:pin_login"), {"worker": worker.pk, "pin": "1357"})
        assert resp.status_code == 302
        assert client.get(reverse("dashboard:home")).status_code == 403
        assert client.get(reverse("staff:home")).status_code == 200


@pytest.fixture
def manager_com_pin_e_worker(client, restaurant, manager):
    manager.set_staff_pin("1357")
    worker = Worker.objects.create(restaurant=restaurant, full_name="Gerente Chefe", user=manager)
    _ativar_dispositivo(client, manager)
    return worker, manager


class TestEcraDePonto:
    def test_home_sem_ficha(self, client, staff_user):
        client.force_login(staff_user)
        resp = client.get(reverse("staff:home"))
        assert resp.status_code == 200
        assert "Falta a ficha de trabalhador" in resp.content.decode()

    def test_home_fora_de_turno_mostra_entrada(self, client, worker_com_pin, staff_user):
        client.force_login(staff_user)
        corpo = client.get(reverse("staff:home")).content.decode()
        assert "Entrada" in corpo
        assert "bg-servico" in corpo

    def test_marcar_alterna_estado(self, client, worker_com_pin, staff_user):
        client.force_login(staff_user)
        resp = client.post(reverse("staff:marcar"), HTTP_HX_REQUEST="true")
        corpo = resp.content.decode()
        assert "Saída" in corpo and "bg-chama" in corpo
        assert worker_com_pin.open_entry is not None
        resp = client.post(reverse("staff:marcar"), HTTP_HX_REQUEST="true")
        corpo = resp.content.decode()
        assert "Entrada" in corpo and "bg-servico" in corpo
        worker_com_pin.refresh_from_db()
        assert worker_com_pin.open_entry is None
        assert worker_com_pin.time_entries.count() == 1

    def test_marcado_em_da_fila_offline(self, client, worker_com_pin, staff_user):
        """A marcação sincronizada guarda o timestamp da marcação, não o
        do envio (requisito da Fase 3)."""
        client.force_login(staff_user)
        ha_duas_horas = timezone.now() - datetime.timedelta(hours=2)
        client.post(
            reverse("staff:marcar"),
            {"marcado_em": ha_duas_horas.isoformat()},
            HTTP_HX_REQUEST="true",
        )
        entry = worker_com_pin.open_entry
        assert entry is not None
        assert abs((entry.check_in - ha_duas_horas).total_seconds()) < 1

    def test_marcado_em_no_futuro_e_recusado(self, client, worker_com_pin, staff_user):
        client.force_login(staff_user)
        futuro = timezone.now() + datetime.timedelta(hours=3)
        client.post(
            reverse("staff:marcar"), {"marcado_em": futuro.isoformat()}, HTTP_HX_REQUEST="true"
        )
        entry = worker_com_pin.open_entry
        assert entry.check_in <= timezone.now()

    def test_totais_do_dia(self, client, worker_com_pin, staff_user):
        agora = timezone.now()
        open_shift(worker=worker_com_pin, at=agora - datetime.timedelta(hours=3, minutes=10))
        client.force_login(staff_user)
        corpo = client.get(reverse("staff:home")).content.decode()
        assert "3h1" in corpo  # 3h10 ou 3h11 conforme o segundo


class TestHistoricoEFerias:
    def test_historico_proprio(self, client, worker_com_pin, staff_user):
        open_shift(worker=worker_com_pin)
        client.force_login(staff_user)
        corpo = client.get(reverse("staff:historico")).content.decode()
        assert "em turno" in corpo

    def test_pedido_de_ferias_em_tres_campos(self, client, worker_com_pin, staff_user):
        client.force_login(staff_user)
        resp = client.post(
            reverse("staff:ferias"),
            {"start_date": "2026-10-01", "end_date": "2026-10-07", "request_note": "casamento"},
        )
        assert resp.status_code == 302
        pedido = VacationRequest.objects.get()
        assert pedido.worker == worker_com_pin
        assert pedido.status == VacationRequest.Status.PENDENTE

    def test_lista_so_mostra_os_proprios_pedidos(self, client, restaurant, worker_com_pin, staff_user):
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


class TestArranqueDaPWA:
    """A PWA arranca em /equipa/ (start_url do manifest). Sem sessão, o
    caminho tem de levar ao PIN — não ao login do backoffice."""

    def test_equipa_sem_sessao_vai_para_o_pin(self, client):
        resp = client.get(reverse("staff:home"))
        assert resp.status_code == 302
        assert reverse("staff:pin_login") in resp.url
        assert reverse("accounts:login") not in resp.url

    def test_todas_as_vistas_staff_vao_para_o_pin(self, client):
        for nome in ["staff:home", "staff:historico", "staff:ferias"]:
            resp = client.get(reverse(nome))
            assert reverse("staff:pin_login") in resp.url, nome

    def test_sair_na_vista_staff_volta_ao_pin(self, client, manager, worker_com_pin, staff_user):
        _ativar_dispositivo(client, manager)
        client.post(reverse("staff:pin_login"), {"worker": worker_com_pin.pk, "pin": "2468"})
        resp = client.post(reverse("accounts:logout"), {"next": reverse("staff:pin_login")})
        assert resp.status_code == 302
        assert resp.url == reverse("staff:pin_login")

    def test_backoffice_continua_a_usar_o_login_de_email(self, client):
        resp = client.get(reverse("dashboard:home"))
        assert reverse("accounts:login") in resp.url


def _entrar_com_pin(client, worker, pin="2468"):
    return client.post(reverse("staff:pin_login"), {"worker": worker.pk, "pin": pin})


class TestModoQuiosque:
    """Tablet partilhado: a sessão PIN termina a seguir a cada marcação
    (secção 5 do plano). Telemóvel pessoal: a sessão mantém-se."""

    def test_shared_device_ends_pin_session_after_mark(self, client, manager, worker_com_pin):
        _ativar_dispositivo(client, manager)
        _entrar_com_pin(client, worker_com_pin)
        resp = client.post(reverse("staff:marcar"), {"acao": "entrada"}, HTTP_HX_REQUEST="true")
        assert resp["HX-Redirect"] == reverse("staff:pin_login")
        assert worker_com_pin.open_entry is not None
        # O colaborador seguinte já não herda a sessão.
        assert client.get(reverse("staff:home")).status_code == 302
        corpo = client.get(reverse("staff:pin_login")).content.decode()
        assert "Marta Silva" in corpo and "Entrada às" in corpo

    def test_confirmacao_so_aparece_uma_vez(self, client, manager, worker_com_pin):
        _ativar_dispositivo(client, manager)
        _entrar_com_pin(client, worker_com_pin)
        client.post(reverse("staff:marcar"), {"acao": "entrada"}, HTTP_HX_REQUEST="true")
        client.get(reverse("staff:pin_login"))
        assert "Entrada às" not in client.get(reverse("staff:pin_login")).content.decode()

    def test_dispositivo_pessoal_mantem_a_sessao(self, client, manager, worker_com_pin):
        client.force_login(manager)
        client.post(reverse("accounts:dispositivo"), {"modo": "pessoal"})
        client.post(reverse("accounts:logout"))
        _entrar_com_pin(client, worker_com_pin)
        resp = client.post(reverse("staff:marcar"), {"acao": "entrada"}, HTTP_HX_REQUEST="true")
        assert "HX-Redirect" not in resp
        assert client.get(reverse("staff:home")).status_code == 200

    def test_sessao_no_tablet_partilhado_expira_depressa(self, client, manager, worker_com_pin):
        from accounts.views import KIOSK_SESSION_AGE

        _ativar_dispositivo(client, manager)
        _entrar_com_pin(client, worker_com_pin)
        assert client.session.get_expiry_age() == KIOSK_SESSION_AGE

    def test_cookie_antigo_sem_modo_conta_como_partilhado(self, client, manager, worker_com_pin):
        from django.core import signing

        from accounts.views import DEVICE_COOKIE

        client.cookies[DEVICE_COOKIE] = signing.dumps({"por": manager.pk}, salt=DEVICE_COOKIE)
        _entrar_com_pin(client, worker_com_pin)
        resp = client.post(reverse("staff:marcar"), {"acao": "entrada"}, HTTP_HX_REQUEST="true")
        assert resp["HX-Redirect"] == reverse("staff:pin_login")

    def test_pagina_do_dispositivo_mostra_o_modo(self, client, manager):
        client.force_login(manager)
        client.post(reverse("accounts:dispositivo"), {"modo": "pessoal"})
        assert "Pessoal" in client.get(reverse("accounts:dispositivo")).content.decode()


class TestFilaOffline:
    """Marcações da fila offline: a ação e quem marcou vão com a marcação,
    e uma recusa devolve um motivo legível (Fase 3)."""

    def _fila(self, client, dados):
        return client.post(reverse("staff:marcar"), dados, HTTP_X_OPERO_FILA="1")

    def test_marcacao_da_fila_aceite(self, client, worker_com_pin, staff_user):
        client.force_login(staff_user)
        resp = self._fila(client, {"acao": "entrada", "trabalhador": worker_com_pin.pk})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert worker_com_pin.open_entry is not None

    def test_rejected_offline_mark_reports_reason(self, client, worker_com_pin, staff_user):
        open_shift(worker=worker_com_pin, at=timezone.now() - datetime.timedelta(hours=1))
        client.force_login(staff_user)
        resp = self._fila(client, {"acao": "entrada", "trabalhador": worker_com_pin.pk})
        assert resp.status_code == 409
        assert "já tem um turno aberto" in resp.json()["texto"]

    def test_acao_desatualizada_nao_e_aplicada_ao_contrario(self, client, worker_com_pin, staff_user):
        """Um botão de saída carregado offline depois de o gerente ter
        fechado o turno não abre um turno novo."""
        client.force_login(staff_user)
        resp = self._fila(client, {"acao": "saida", "trabalhador": worker_com_pin.pk})
        assert resp.status_code == 409
        assert worker_com_pin.open_entry is None
        assert worker_com_pin.time_entries.count() == 0

    def test_marcacao_de_outro_colaborador_recusada(self, client, restaurant, worker_com_pin, staff_user):
        outro = Worker.objects.create(restaurant=restaurant, full_name="Rui Costa")
        client.force_login(staff_user)
        resp = self._fila(client, {"acao": "entrada", "trabalhador": outro.pk})
        assert resp.status_code == 409
        assert "outro colaborador" in resp.json()["texto"]
        assert worker_com_pin.open_entry is None

    def test_fila_no_tablet_partilhado_termina_a_sessao(self, client, manager, worker_com_pin):
        _ativar_dispositivo(client, manager)
        _entrar_com_pin(client, worker_com_pin)
        resp = self._fila(client, {"acao": "entrada", "trabalhador": worker_com_pin.pk})
        assert resp.json()["sessao_terminada"] is True
        assert client.get(reverse("staff:home")).status_code == 302

    def test_formulario_leva_acao_e_trabalhador(self, client, worker_com_pin, staff_user):
        client.force_login(staff_user)
        corpo = client.get(reverse("staff:home")).content.decode()
        assert 'name="acao" value="entrada"' in corpo
        assert f'name="trabalhador" value="{worker_com_pin.pk}"' in corpo
        assert f'data-trabalhador="{worker_com_pin.pk}"' in corpo
