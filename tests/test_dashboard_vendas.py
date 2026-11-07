"""Tarefa C6: o cartão de vendas não mostra um zero que se lê como «zero
vendas», e os meses escrevem-se por extenso e em minúsculas."""
import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from core.utils import nome_do_mes
from dashboard.views import cartao_vendas

HOJE = datetime.date(2026, 11, 7)


def test_cartao_vendas_sem_importacoes():
    assert cartao_vendas(Decimal(0), None, HOJE) == {"valor": None, "legenda": "Ainda não há vendas importadas"}


def test_cartao_vendas_mes_ainda_sem_dados():
    c = cartao_vendas(Decimal(0), datetime.date(2026, 10, 25), HOJE)
    assert c == {"valor": None, "legenda": "Sem vendas de novembro · último dia 25/10"}


def test_cartao_vendas_com_dados():
    c = cartao_vendas(Decimal("812.40"), datetime.date(2026, 11, 5), HOJE)
    assert c == {"valor": Decimal("812.40"), "legenda": "Vendas de novembro · até 05/11"}


def test_cartao_vendas_com_so_o_dia_1_importado():
    c = cartao_vendas(Decimal("95.00"), datetime.date(2026, 11, 1), HOJE)
    assert c == {"valor": Decimal("95.00"), "legenda": "Vendas de novembro · até 01/11"}


def test_nome_do_mes_em_minusculas():
    meses = [nome_do_mes(datetime.date(2026, m, 1)) for m in (1, 3, 10, 12)]
    assert meses == ["janeiro", "março", "outubro", "dezembro"]


@pytest.mark.django_db
def test_dashboard_sem_vendas_mostra_traco_e_leva_a_importar(client, manager):
    client.force_login(manager)
    html = client.get(reverse("dashboard:home")).content.decode()
    assert f'<a href="{reverse("sales:importar")}" class="cartao cartao-link' in html
    assert "Ainda não há vendas importadas" in html


@pytest.mark.django_db
def test_painel_do_grupo_usa_o_cartao_de_vendas(client, restaurant):
    dono = get_user_model().objects.create_user(
        email="dono@tasca.pt", password="segredo-de-teste-123", organization=restaurant.organization, is_group_admin=True
    )
    client.force_login(dono)
    resp = client.get(reverse("grupo:painel"))
    assert resp.context["linhas"][0]["vendas"] == {"valor": None, "legenda": "Ainda não há vendas importadas"}
    assert "Ainda não há vendas importadas" in resp.content.decode()
