"""As páginas de erro têm o aspeto da app e uma única saída: voltar ao início."""
import pytest
from django.template import loader
from django.test import Client
from django.urls import reverse


def test_403_tem_o_aspeto_da_app(client, stock_user):
    client.force_login(stock_user)
    r = client.get(reverse("workers:lista"))
    assert r.status_code == 403
    html = r.content.decode()
    assert "Não tem acesso a esta página" in html
    assert "O seu perfil nesta casa não abre esta área." in html
    assert 'href="/"' in html


def test_404_tem_o_aspeto_da_app(client, manager):
    client.force_login(manager)
    r = client.get("/gestao/nao-existe/")
    assert r.status_code == 404
    html = r.content.decode()
    assert "Esta página não existe" in html
    assert "O endereço pode estar errado ou a página foi removida." in html
    assert 'href="/"' in html


def test_500_mostra_se_sem_contexto():
    html = loader.get_template("500.html").render()
    assert "Algo correu mal" in html
    assert "O erro ficou registado. Tente de novo daqui a pouco." in html
    assert 'href="/"' in html


def test_500_real_usa_a_pagina_da_app(restaurant, manager):
    cliente = Client(raise_request_exception=False)
    cliente.force_login(manager)
    from unittest import mock

    with mock.patch("dashboard.views.DashboardView.get_context_data", side_effect=RuntimeError("falha")):
        r = cliente.get(reverse("dashboard:home"))
    assert r.status_code == 500
    assert "Algo correu mal" in r.content.decode()


def test_falha_de_csrf_fora_do_login_mostra_a_pagina_da_app(restaurant, manager):
    cliente = Client(enforce_csrf_checks=True)
    cliente.force_login(manager)
    r = cliente.post(reverse("accounts:logout"))
    assert r.status_code == 403
    html = r.content.decode()
    assert "A página expirou" in html
    assert "Volte atrás, recarregue a página e repita." in html
    assert 'href="/"' in html
    assert "CSRF" not in html


@pytest.mark.parametrize("nome", ["403.html", "404.html", "500.html", "403_csrf.html"])
def test_paginas_de_erro_sao_documentos_completos(nome):
    html = loader.get_template(nome).render()
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert 'lang="pt"' in html
    assert "css/app.css" in html
