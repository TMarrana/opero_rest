"""Fase 7: código de ponto e conta da app geridos a partir da ficha do
trabalhador, e a password provisória que se muda no primeiro login."""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from workers.models import Worker
from workers.views import password_provisoria

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def joana(restaurant):
    return Worker.objects.create(restaurant=restaurant, full_name="Joana Pires Lopes")


def _criar_conta(client, worker, email="joana@tasca.pt", role="STAFF"):
    return client.post(reverse("workers:conta", args=[worker.pk]), {"acao": "criar", "email": email, "role": role})


class TestCodigoDePonto:
    def test_gerente_define_codigo_sem_conta(self, client, manager, joana):
        client.force_login(manager)
        resp = client.post(reverse("workers:codigo", args=[joana.pk]), {"codigo": "4321"})
        assert resp.status_code == 302
        joana.refresh_from_db()
        assert joana.user is None
        assert joana.check_kiosk_code("4321") and not joana.check_kiosk_code("1234")
        assert joana.kiosk_code != "4321"  # guardado com hash

    def test_codigo_tem_4_a_6_algarismos(self, client, manager, joana):
        client.force_login(manager)
        for invalido in ["123", "1234567", "12a4"]:
            resp = client.post(reverse("workers:codigo", args=[joana.pk]), {"codigo": invalido})
            assert "4 a 6 algarismos" in resp.content.decode()
        joana.refresh_from_db()
        assert not joana.has_code

    def test_colaborador_e_stock_nao_definem_codigos(self, client, staff_user, stock_user, joana):
        for user in [staff_user, stock_user]:
            client.force_login(user)
            assert client.get(reverse("workers:codigo", args=[joana.pk])).status_code == 403

    def test_lista_mostra_codigo_e_conta(self, client, manager, joana):
        client.force_login(manager)
        corpo = client.get(reverse("workers:lista")).content.decode()
        assert "Definir código" in corpo and "Dar acesso à app" in corpo


class TestContaDaApp:
    def test_gerente_cria_conta_com_password_provisoria(self, client, manager, joana):
        client.force_login(manager)
        resp = _criar_conta(client, joana)
        assert resp.status_code == 200
        assert resp["Cache-Control"] == "no-store"
        password = resp.context["password"]
        assert password in resp.content.decode()
        joana.refresh_from_db()
        conta = joana.user
        assert conta.email == "joana@tasca.pt"
        assert conta.role == User.Role.STAFF
        assert conta.restaurant == joana.restaurant
        assert (conta.first_name, conta.last_name) == ("Joana", "Pires Lopes")
        assert conta.must_change_password
        assert conta.check_password(password)

    def test_email_repetido_recusado(self, client, manager, joana, staff_user):
        client.force_login(manager)
        resp = _criar_conta(client, joana, email=staff_user.email.upper())
        assert "Já existe uma conta com este email" in resp.content.decode()
        joana.refresh_from_db()
        assert joana.user is None

    def test_manager_cannot_manage_manager_accounts(self, client, restaurant, manager, joana):
        """Secção 7: o gerente só cria e gere contas de Colaborador e Resp.
        stock; as de Gerente e Admin são do admin."""
        client.force_login(manager)
        for role in ["MANAGER", "ADMIN"]:
            resp = _criar_conta(client, joana, role=role)
            assert resp.status_code == 200 and "password" not in resp.context
        joana.refresh_from_db()
        assert joana.user is None

        outro_gerente = User.objects.create_user(
            email="outro@tasca.pt", password="x-segredo-123", restaurant=restaurant, role=User.Role.MANAGER
        )
        ficha = Worker.objects.create(restaurant=restaurant, full_name="Outro Gerente", user=outro_gerente)
        resp = client.post(reverse("workers:conta", args=[ficha.pk]), {"acao": "repor"})
        assert resp.status_code == 302
        outro_gerente.refresh_from_db()
        assert outro_gerente.check_password("x-segredo-123") and not outro_gerente.must_change_password
        corpo = client.get(reverse("workers:conta", args=[ficha.pk])).content.decode()
        assert "só o administrador as gere" in corpo

    def test_gerente_nao_promove_a_gerente(self, client, manager, joana):
        client.force_login(manager)
        _criar_conta(client, joana)
        joana.refresh_from_db()
        client.post(reverse("workers:conta", args=[joana.pk]), {"acao": "perfil", "role": "MANAGER"})
        joana.user.refresh_from_db()
        assert joana.user.role == User.Role.STAFF
        client.post(reverse("workers:conta", args=[joana.pk]), {"acao": "perfil", "role": "STOCK"})
        joana.user.refresh_from_db()
        assert joana.user.role == User.Role.STOCK

    def test_admin_cria_conta_de_gerente(self, client, admin_user, joana):
        client.force_login(admin_user)
        _criar_conta(client, joana, role="MANAGER")
        joana.refresh_from_db()
        assert joana.user.role == User.Role.MANAGER

    def test_ninguem_repoe_a_propria_password_aqui(self, client, restaurant, admin_user):
        ficha = Worker.objects.create(restaurant=restaurant, full_name="Admin Dono", user=admin_user)
        client.force_login(admin_user)
        client.post(reverse("workers:conta", args=[ficha.pk]), {"acao": "repor"})
        admin_user.refresh_from_db()
        assert not admin_user.must_change_password

    def test_repor_gera_nova_provisoria(self, client, manager, joana):
        client.force_login(manager)
        primeira = _criar_conta(client, joana).context["password"]
        resp = client.post(reverse("workers:conta", args=[joana.pk]), {"acao": "repor"})
        nova = resp.context["password"]
        joana.refresh_from_db()
        assert nova != primeira
        assert joana.user.check_password(nova) and not joana.user.check_password(primeira)
        assert joana.user.must_change_password

    def test_password_provisoria_facil_de_ditar(self):
        password = password_provisoria()
        grupos = password.split("-")
        assert len(grupos) == 3 and all(len(g) == 4 for g in grupos)
        assert not set(password) & set("01ilo")


class TestPasswordProvisoria:
    def _conta_provisoria(self, client, manager, joana):
        client.force_login(manager)
        password = _criar_conta(client, joana).context["password"]
        client.post(reverse("accounts:logout"))
        joana.refresh_from_db()
        return password

    def test_temporary_password_must_be_changed(self, client, manager, joana):
        password = self._conta_provisoria(client, manager, joana)
        resp = client.post(reverse("accounts:login"), {"username": "joana@tasca.pt", "password": password}, follow=True)
        assert resp.redirect_chain[-1][0] == reverse("accounts:definir_password")
        for url in [reverse("staff:home"), reverse("staff:ferias")]:
            resp = client.get(url)
            assert resp.status_code == 302 and resp.url == reverse("accounts:definir_password")

    def test_mudar_a_password_liberta_a_app(self, client, manager, joana):
        password = self._conta_provisoria(client, manager, joana)
        client.post(reverse("accounts:login"), {"username": "joana@tasca.pt", "password": password})
        resp = client.post(
            reverse("accounts:definir_password"),
            {"new_password1": "cozinha-quente-42", "new_password2": "cozinha-quente-42"},
        )
        assert resp.status_code == 302
        joana.user.refresh_from_db()
        assert not joana.user.must_change_password
        assert joana.user.check_password("cozinha-quente-42")
        # A sessão continua válida depois de mudar a password.
        assert client.get(reverse("staff:home")).status_code == 200

    def test_password_fraca_recusada(self, client, manager, joana):
        password = self._conta_provisoria(client, manager, joana)
        client.post(reverse("accounts:login"), {"username": "joana@tasca.pt", "password": password})
        resp = client.post(reverse("accounts:definir_password"), {"new_password1": "12345678", "new_password2": "12345678"})
        assert resp.status_code == 200
        joana.user.refresh_from_db()
        assert joana.user.must_change_password

    def test_sair_continua_possivel(self, client, manager, joana):
        password = self._conta_provisoria(client, manager, joana)
        client.post(reverse("accounts:login"), {"username": "joana@tasca.pt", "password": password})
        resp = client.post(reverse("accounts:logout"))
        assert resp.status_code == 302 and resp.url == reverse("accounts:login")
