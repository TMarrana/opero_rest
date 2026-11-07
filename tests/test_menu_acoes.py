"""Tarefa D3: cada linha das listas tem uma ação visível (verde) e as outras
no menu «Mais ações»."""
import pytest
from django.urls import reverse

from inventory.models import Category, Item
from workers.models import Worker

pytestmark = pytest.mark.django_db


def _linha(html, inicio):
    i = html.index(inicio)
    return html[i:html.index("</tr>", i)]


def _visivel_e_menu(linha):
    """O que está antes do botão «Mais ações» e o que está dentro do menu."""
    assert linha.count('aria-haspopup="true"') == 1
    visivel, menu = linha.split('aria-haspopup="true"')
    assert "Mais ações" in menu
    return visivel, menu


def test_stock_mostra_movimento_e_o_resto_em_mais_acoes(client, restaurant, stock_user):
    categoria = Category.objects.get_or_create(restaurant=restaurant, name="Mercearia")[0]
    item = Item.objects.create(restaurant=restaurant, name="Arroz", unit="KG", category=categoria)
    client.force_login(stock_user)
    linha = _linha(client.get(reverse("inventory:lista")).content.decode(), f'id="item-{item.pk}"')
    visivel, menu = _visivel_e_menu(linha)
    assert "btn-primario" in visivel and ">Movimento<" in visivel
    assert reverse("purchasing:precos", args=[item.pk]) in menu
    assert reverse("inventory:editar", args=[item.pk]) in menu


def test_trabalhadores_mostram_editar_e_o_codigo_e_a_conta_em_mais_acoes(client, restaurant, manager):
    w = Worker.objects.create(restaurant=restaurant, full_name="Marta Silva")
    client.force_login(manager)
    linha = _linha(client.get(reverse("workers:lista")).content.decode(), "Marta Silva")
    visivel, menu = _visivel_e_menu(linha)
    assert "btn-primario" in visivel and reverse("workers:editar", args=[w.pk]) in visivel
    assert reverse("workers:codigo", args=[w.pk]) in menu
    assert reverse("workers:conta", args=[w.pk]) in menu
