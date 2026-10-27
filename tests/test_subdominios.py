"""Isolamento entre clientes por subdomínio (decidido a 2026-10-27): cada
grupo entra em <endereço>.OPERO_BASE_DOMAIN, e uma conta, uma sessão ou um
tablet de outro grupo não passam."""
import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from core.models import Organization, Restaurant
from core.middleware import subdomain_of
from workers.models import Worker

from .quiosque import ativar_tablet

pytestmark = pytest.mark.django_db

User = get_user_model()
BASE = "opero.test"
PASSWORD = "segredo-de-teste-123"


@pytest.fixture(autouse=True)
def subdominios(settings):
    settings.OPERO_BASE_DOMAIN = BASE
    settings.ALLOWED_HOSTS = [f".{BASE}", BASE]


@pytest.fixture
def outra(db):
    """Outro cliente, com uma casa e um gerente."""
    casa = Restaurant.objects.create(name="Marisqueira da Foz", slug="foz")
    gerente = User.objects.create_user(
        email="gerente@foz.pt", password=PASSWORD, restaurant=casa, role=User.Role.MANAGER
    )
    return casa, gerente


def _host(grupo):
    return {"HTTP_HOST": f"{grupo.subdomain}.{BASE}"}


class TestEndereco:
    def test_gerado_do_nome_e_unico(self, restaurant):
        assert restaurant.organization.subdomain == "tasca-do-teste"
        outro = Organization.objects.create(name="Tasca do Teste")
        assert outro.subdomain == "tasca-do-teste-2"
        assert Organization.objects.create(name="App").subdomain == "app-grupo"
        assert restaurant.organization.address == f"tasca-do-teste.{BASE}"

    def test_validacao(self):
        grupo = Organization(name="X", subdomain="Tasca_Zé")
        with pytest.raises(ValidationError):
            grupo.full_clean()
        grupo.subdomain = "www"
        with pytest.raises(ValidationError):
            grupo.full_clean()

    def test_subdominio_do_host(self):
        assert subdomain_of(f"tasca.{BASE}:8000", BASE) == "tasca"
        assert subdomain_of(BASE, BASE) is None
        assert subdomain_of(f"www.{BASE}", BASE) is None
        assert subdomain_of("outro.pt", BASE) is None


class TestEntrada:
    def test_endereco_desconhecido_da_404(self, client, restaurant):
        assert client.get(reverse("accounts:login"), HTTP_HOST=f"nao-existe.{BASE}").status_code == 404

    def test_grupo_inativo_da_404(self, client, restaurant):
        restaurant.organization.is_active = False
        restaurant.organization.save()
        assert client.get(reverse("accounts:login"), **_host(restaurant.organization)).status_code == 404

    def test_login_no_proprio_grupo(self, client, restaurant, manager):
        resp = client.get(reverse("accounts:login"), **_host(restaurant.organization))
        assert "Tasca do Teste · Entre com o email" in resp.content.decode()
        resp = client.post(
            reverse("accounts:login"), {"username": manager.email, "password": PASSWORD}, **_host(restaurant.organization)
        )
        assert resp.status_code == 302
        assert client.get(reverse("dashboard:home"), **_host(restaurant.organization)).status_code == 200

    def test_conta_de_outro_grupo_nao_entra(self, client, restaurant, outra):
        _, gerente_foz = outra
        resp = client.post(
            reverse("accounts:login"), {"username": gerente_foz.email, "password": PASSWORD}, **_host(restaurant.organization)
        )
        assert resp.status_code == 200
        assert "Email ou palavra-passe errados" in resp.content.decode()

    def test_sessao_de_outro_grupo_e_posta_fora(self, client, restaurant, outra):
        _, gerente_foz = outra
        client.force_login(gerente_foz)
        resp = client.get(reverse("dashboard:home"), **_host(restaurant.organization))
        assert resp.status_code == 302 and resp["Location"] == reverse("accounts:login")
        assert "_auth_user_id" not in client.session

    def test_superutilizador_entra_em_todos(self, client, restaurant):
        dono = User.objects.create_superuser(email="plataforma@opero.pt", password=PASSWORD)
        resp = client.post(
            reverse("accounts:login"), {"username": dono.email, "password": PASSWORD}, **_host(restaurant.organization)
        )
        assert resp.status_code == 302


class TestDominioSemGrupo:
    def test_leva_a_pagina_do_endereco(self, client, restaurant):
        resp = client.get(reverse("dashboard:home"), HTTP_HOST=BASE)
        assert resp.status_code == 302 and resp["Location"] == reverse("accounts:endereco")
        resp = client.get(reverse("accounts:endereco"), HTTP_HOST=f"www.{BASE}")
        assert "Endereço do restaurante" in resp.content.decode()

    def test_encaminha_para_o_endereco_do_grupo(self, client, restaurant):
        resp = client.post(reverse("accounts:endereco"), {"endereco": " Tasca-do-Teste "}, HTTP_HOST=BASE)
        assert resp.status_code == 302
        assert resp["Location"] == f"http://tasca-do-teste.{BASE}/conta/entrar/"
        resp = client.post(reverse("accounts:endereco"), {"endereco": f"tasca-do-teste.{BASE}"}, HTTP_HOST=BASE)
        assert resp["Location"] == f"http://tasca-do-teste.{BASE}/conta/entrar/"

    def test_endereco_errado(self, client, restaurant):
        resp = client.post(reverse("accounts:endereco"), {"endereco": "nao-existe"}, HTTP_HOST=BASE)
        assert resp.status_code == 400
        assert "Não há nenhum restaurante neste endereço" in resp.content.decode()

    def test_admin_da_plataforma_continua_no_dominio(self, client):
        assert client.get("/admin/login/", HTTP_HOST=BASE).status_code == 200


class TestQuiosque:
    def test_tablet_de_outro_grupo_nao_abre(self, client, restaurant, manager, outra):
        casa_foz, _ = outra
        Worker.objects.create(restaurant=restaurant, full_name="Marta Silva").set_kiosk_code("2468")
        client.defaults.update(_host(restaurant.organization))
        ativar_tablet(client, manager)
        assert client.get(reverse("kiosk:inicio")).status_code == 200
        # O mesmo cookie num endereço de outro grupo não abre o quiosque.
        resp = client.get(reverse("kiosk:inicio"), **_host(casa_foz.organization))
        assert resp.status_code == 403


class TestSemDominioBase:
    def test_tudo_num_so_endereco(self, client, settings, manager):
        settings.OPERO_BASE_DOMAIN = ""
        settings.ALLOWED_HOSTS = ["testserver"]
        client.force_login(manager)
        assert client.get(reverse("dashboard:home")).status_code == 200
        assert client.get(reverse("accounts:endereco")).status_code == 302
