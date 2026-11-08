"""Fase 0: login e redirecionamento por perfil."""
import pytest
from django.urls import reverse, reverse_lazy

pytestmark = pytest.mark.django_db


def test_login_page_renders(client):
    resp = client.get(reverse("accounts:login"))
    assert resp.status_code == 200


def test_login_com_campo_de_email(client):
    html = client.get(reverse("accounts:login")).content.decode()
    assert 'type="email"' in html and 'autocomplete="username"' in html


def test_campo_de_email_sem_correcoes_e_com_o_foco_e_o_limite_do_django():
    from accounts.forms import LoginForm

    attrs = LoginForm().fields["username"].widget.attrs
    assert (attrs["inputmode"], attrs["autocapitalize"], attrs["spellcheck"]) == ("email", "none", "false")
    # Trocar o widget não pode perder o que o AuthenticationForm lá pôs.
    assert attrs["autofocus"] and attrs["maxlength"]


def test_login_com_email_redireciona_gerente_para_backoffice(client, manager):
    resp = client.post(
        reverse("accounts:login"),
        {"username": "gerente@tasca.pt", "password": "segredo-de-teste-123"},
        follow=True,
    )
    assert resp.redirect_chain[-1][0] == reverse("dashboard:home")
    assert resp.status_code == 200


def test_login_redireciona_colaborador_para_vista_staff(client, staff_user):
    resp = client.post(
        reverse("accounts:login"),
        {"username": "colaborador@tasca.pt", "password": "segredo-de-teste-123"},
        follow=True,
    )
    assert resp.redirect_chain[-1][0] == reverse("staff:home")


def test_colaborador_nao_acede_ao_backoffice(client, staff_user):
    client.force_login(staff_user)
    resp = client.get(reverse("dashboard:home"))
    assert resp.status_code == 403


def test_anonimo_e_reencaminhado_para_login(client):
    resp = client.get(reverse("dashboard:home"))
    assert resp.status_code == 302
    assert reverse("accounts:login") in resp.url


def test_gerente_tambem_ve_a_app_do_colaborador(client, manager):
    """A app serve qualquer conta: o gerente vê lá os próprios turnos. O
    código de ponto nunca abre sessão (test_staff.py)."""
    client.force_login(manager)
    assert client.get(reverse("staff:home")).status_code == 200


def test_perfis_de_backoffice_veem_o_dashboard(client, admin_user, stock_user):
    for user in [admin_user, stock_user]:
        client.force_login(user)
        assert client.get(reverse("dashboard:home")).status_code == 200


def test_role_sincroniza_grupo(manager):
    assert manager.groups.filter(name="Gerente").exists()
    manager.role = manager.Role.STOCK
    manager.save()
    assert manager.groups.filter(name="Responsável de stock").exists()
    assert not manager.groups.filter(name="Gerente").exists()


def test_pagina_de_componentes_renderiza(client, manager):
    """Aceitação da Fase 0: a página de componentes mostra os elementos."""
    client.force_login(manager)
    resp = client.get(reverse("core:components"))
    assert resp.status_code == 200
    corpo = resp.content.decode()
    for elemento in ["Botão", "Campo", "Badge", "Talão", "Tabela", "Modal", "Toast"]:
        assert elemento in corpo


def _form_login(client, url):
    import re

    resp = client.get(url)
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', resp.content.decode()).group(1)
    return {"username": "colaborador@tasca.pt", "password": "segredo-de-teste-123", "csrfmiddlewaretoken": token}


def test_segundo_envio_do_login_segue_para_a_app_em_vez_de_403(staff_user):
    """O login roda o token CSRF: um duplo toque no telemóvel mandava o
    segundo envio com o token antigo e dava 403 com a sessão já aberta."""
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    url = reverse("accounts:login") + "?next=/equipa/"
    dados = _form_login(client, url)
    assert client.post(url, dados).status_code == 302
    resp = client.post(url, dados)
    assert resp.status_code == 302
    assert resp.url == "/equipa/"


def test_login_com_token_caducado_volta_ao_formulario(staff_user):
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    url = reverse("accounts:login")
    dados = _form_login(client, url)
    dados["csrfmiddlewaretoken"] = "x" * 64
    resp = client.post(url, dados)
    assert resp.status_code == 302
    assert resp.url == url
    assert "_auth_user_id" not in client.session


def test_falha_csrf_fora_do_login_continua_403(staff_user):
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    client.force_login(staff_user)
    resp = client.post(reverse("accounts:logout"))
    assert resp.status_code == 403


def test_sair_limpa_a_cache_do_telemovel(client, staff_user):
    client.force_login(staff_user)
    r = client.post(reverse("accounts:logout"))
    assert r["Clear-Site-Data"] == '"cache", "storage"'
    assert r.status_code == 302 and r.url == reverse("accounts:login")
    assert "_auth_user_id" not in client.session


class TestLimiteLogin:
    URL = reverse_lazy("accounts:login")

    def test_dez_falhas_bloqueiam_o_email(self, client, manager):
        for _ in range(10):
            client.post(self.URL, {"username": "gerente@tasca.pt", "password": "errada"})
        r = client.post(self.URL, {"username": "GERENTE@tasca.pt", "password": "segredo-de-teste-123"})
        assert "Demasiadas tentativas" in r.content.decode()
        assert "_auth_user_id" not in client.session

    def test_entrar_bem_limpa_as_falhas(self, client, manager):
        for _ in range(9):
            client.post(self.URL, {"username": "gerente@tasca.pt", "password": "errada"})
        client.post(self.URL, {"username": "gerente@tasca.pt", "password": "segredo-de-teste-123"})
        client.logout()
        client.post(self.URL, {"username": "gerente@tasca.pt", "password": "errada"})
        r = client.post(self.URL, {"username": "gerente@tasca.pt", "password": "segredo-de-teste-123"})
        assert r.status_code == 302

    def test_bloqueio_e_por_email_e_ip(self, client, manager):
        """Quem erra de outro sitio nao bloqueia o dono da conta."""
        for _ in range(10):
            client.post(self.URL, {"username": "gerente@tasca.pt", "password": "errada"}, REMOTE_ADDR="203.0.113.9")
        r = client.post(self.URL, {"username": "gerente@tasca.pt", "password": "segredo-de-teste-123"},
                        REMOTE_ADDR="198.51.100.4")
        assert r.status_code == 302

    def test_atras_do_proxy_conta_o_ip_que_o_proxy_viu(self, client, manager):
        """O ultimo X-Forwarded-For e o que o proxy acrescentou; os anteriores
        vem do cliente e podiam mudar a cada tentativa."""
        for i in range(10):
            client.post(self.URL, {"username": "gerente@tasca.pt", "password": "errada"},
                        HTTP_X_FORWARDED_FOR=f"10.0.0.{i}, 203.0.113.9")
        r = client.post(self.URL, {"username": "gerente@tasca.pt", "password": "segredo-de-teste-123"},
                        HTTP_X_FORWARDED_FOR="10.9.9.9, 203.0.113.9")
        assert "Demasiadas tentativas" in r.content.decode()

    def test_bloqueio_e_um_erro_geral_do_formulario(self, client, manager):
        for _ in range(10):
            client.post(self.URL, {"username": "gerente@tasca.pt", "password": "errada"})
        r = client.post(self.URL, {"username": "gerente@tasca.pt", "password": "segredo-de-teste-123"})
        form = r.context["form"]
        assert form.non_field_errors() and not form.errors.get("username")
