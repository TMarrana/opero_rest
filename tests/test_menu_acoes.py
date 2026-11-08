"""Tarefa D3: cada linha das listas tem uma ação visível (verde) e as outras
no menu «Mais ações»."""
from html.parser import HTMLParser

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


class _ClassesAcimaDoPainel(HTMLParser):
    """Para cada painel «Mais ações» da página, as classes de todos os
    elementos que o contêm, do <html> até à <div> do menu."""

    VAZIOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self):
        super().__init__()
        self.abertos, self.paineis = [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if (attrs.get("id") or "").startswith("menu-acoes-"):
            self.paineis.append([c for _, classes in self.abertos for c in classes.split()])
        if tag not in self.VAZIOS:
            self.abertos.append((tag, attrs.get("class") or ""))

    def handle_endtag(self, tag):
        for i in range(len(self.abertos) - 1, -1, -1):
            if self.abertos[i][0] == tag:
                del self.abertos[i:]
                return


def _translucidas_acima_do_painel(html):
    leitor = _ClassesAcimaDoPainel()
    leitor.feed(html)
    [acima] = leitor.paineis
    return [c for c in acima if c.startswith("opacity-")]


def test_artigo_inativo_fica_esbatido_mas_o_menu_nao(client, restaurant, stock_user):
    """Um `opacity` na linha passa para tudo o que ela contém, também para o
    painel do menu, que ficava translúcido por cima das linhas seguintes."""
    categoria = Category.objects.get_or_create(restaurant=restaurant, name="Mercearia")[0]
    item = Item.objects.create(restaurant=restaurant, name="Arroz", unit="KG", category=categoria, is_active=False)
    client.force_login(stock_user)
    html = client.get(reverse("inventory:lista")).content.decode()
    assert _translucidas_acima_do_painel(html) == []
    assert "opacity-50" in _linha(html, f'id="item-{item.pk}"')


def test_trabalhador_inativo_fica_esbatido_mas_o_menu_nao(client, restaurant, manager):
    Worker.objects.create(restaurant=restaurant, full_name="Marta Silva", is_active=False)
    client.force_login(manager)
    html = client.get(reverse("workers:lista") + "?inativos=1").content.decode()
    assert _translucidas_acima_do_painel(html) == []
    assert "opacity-50" in _linha(html, "Marta Silva")


def test_cada_menu_tem_o_nome_da_linha_no_nome_acessivel(client, restaurant, stock_user, manager):
    categoria = Category.objects.get_or_create(restaurant=restaurant, name="Mercearia")[0]
    Item.objects.create(restaurant=restaurant, name="Arroz", unit="KG", category=categoria)
    client.force_login(stock_user)
    assert 'aria-label="Mais ações: Arroz"' in client.get(reverse("inventory:lista")).content.decode()
    Worker.objects.create(restaurant=restaurant, full_name="Marta Silva")
    client.force_login(manager)
    assert 'aria-label="Mais ações: Marta Silva"' in client.get(reverse("workers:lista")).content.decode()


def test_linha_devolvida_depois_do_movimento_mantem_o_menu(client, restaurant, stock_user):
    categoria = Category.objects.get_or_create(restaurant=restaurant, name="Mercearia")[0]
    item = Item.objects.create(restaurant=restaurant, name="Arroz", unit="KG", category=categoria)
    client.force_login(stock_user)
    resp = client.post(
        reverse("inventory:movimento", args=[item.pk]),
        {"movement_type": "ENTRADA", "quantity": "2", "occurred_at": "2026-09-04T10:00"},
        HTTP_HX_REQUEST="true",
    )
    linha = _linha(resp.content.decode(), f'id="item-{item.pk}"')
    visivel, menu = _visivel_e_menu(linha)
    assert ">Movimento<" in visivel and reverse("inventory:editar", args=[item.pk]) in menu


def test_menu_acoes_esta_na_pagina_de_componentes(client, stock_user):
    client.force_login(stock_user)
    html = client.get(reverse("core:components")).content.decode()
    assert 'aria-haspopup="true"' in html and "Mais ações" in html


def test_painel_fecha_quando_a_tabela_rola_na_horizontal(client, restaurant, stock_user):
    """O painel é fixed: se a tabela rolar por baixo, fecha em vez de ficar
    pendurado longe do botão."""
    categoria = Category.objects.get_or_create(restaurant=restaurant, name="Mercearia")[0]
    Item.objects.create(restaurant=restaurant, name="Arroz", unit="KG", category=categoria)
    client.force_login(stock_user)
    html = client.get(reverse("inventory:lista")).content.decode()
    assert "closest('.overflow-x-auto')" in html
