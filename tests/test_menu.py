"""O menu e as views leem o mesmo mapa de permissões (core/permissions.py):
cada perfil só vê no menu o que consegue abrir."""
import re

import pytest
from django.urls import reverse

from accounts.models import User
from accounts.services import dar_acesso
from core.models import Restaurant

PERFIS = ["admin_user", "manager", "stock_user"]


@pytest.mark.parametrize("perfil", PERFIS)
def test_cada_ligacao_do_menu_abre(client, perfil, request):
    client.force_login(request.getfixturevalue(perfil))
    html = client.get(reverse("dashboard:home")).content.decode()
    menu = html[html.index('aria-label="Navegação principal"'):]
    menu = menu[: menu.index("</nav>")]
    ligacoes = set(re.findall(r'href="(/[^"]+)"', menu))
    assert ligacoes
    for href in ligacoes:
        assert client.get(href).status_code in (200, 302), href


def test_resp_stock_nao_ve_as_areas_de_pessoas(client, stock_user):
    client.force_login(stock_user)
    html = client.get(reverse("dashboard:home")).content.decode()
    for nome in ("workers:lista", "attendance:dia", "vacations:calendario", "shifts:planeador", "accounts:dispositivo"):
        assert f'href="{reverse(nome)}"' not in html
    assert f'href="{reverse("inventory:lista")}"' in html


def test_menu_segue_o_perfil_da_casa_ativa(client, restaurant, stock_user):
    outra = Restaurant.objects.create(name="Tasca Dois", slug="tasca-dois", organization=restaurant.organization)
    dar_acesso(stock_user, outra, User.Role.MANAGER)
    client.force_login(stock_user)
    client.post(reverse("dashboard:mudar_casa"), {"casa": outra.pk})
    html = client.get(reverse("dashboard:home")).content.decode()
    assert f'href="{reverse("attendance:dia")}"' in html


def test_secoes_visiveis_por_perfil():
    from core import permissions

    assert permissions.secoes_visiveis(None) == frozenset()
    assert permissions.secoes_visiveis("INEXISTENTE") == frozenset()
    assert permissions.secoes_visiveis(User.Role.STAFF) == frozenset()
    assert permissions.secoes_visiveis(User.Role.ADMIN) == frozenset(permissions.SECOES)
    assert "configuracao" not in permissions.secoes_visiveis(User.Role.MANAGER)
    assert permissions.secoes_visiveis(User.Role.STOCK) == {"dashboard", "stock", "compras", "fichas", "analise"}


def test_conjuntos_de_perfis():
    from core import permissions

    assert permissions.ADMIN == {User.Role.ADMIN}
    assert permissions.PESSOAS == {User.Role.ADMIN, User.Role.MANAGER}
    assert permissions.STOCK == {User.Role.ADMIN, User.Role.MANAGER, User.Role.STOCK}
