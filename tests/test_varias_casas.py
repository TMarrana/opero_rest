"""Fase 9: várias casas no mesmo grupo. Cada pedido trabalha numa casa, o
perfil vale por casa, e nada de uma casa aparece noutra."""
import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from accounts.models import Membership
from accounts.services import dar_acesso, tirar_acesso
from attendance.services import open_shift, request_correction
from core.middleware import SESSION_KEY
from core.models import Organization, Restaurant, WorkArea
from inventory.models import Category, Item, StockMovement
from inventory.services import register_movement, transfer_stock
from tests.quiosque import ativar_tablet
from vacations.models import AbsenceType
from vacations.services import create_request
from workers.models import Worker

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def casa_b(restaurant):
    return Restaurant.objects.create(organization=restaurant.organization, name="Tasca da Baixa", slug="tasca-da-baixa")


@pytest.fixture
def dono(restaurant):
    return User.objects.create_user(
        email="dono@tasca.pt", password="segredo-de-teste-123", organization=restaurant.organization, is_group_admin=True
    )


def _artigo(restaurant, nome="Arroz", unidade=Item.Unit.KG, stock=None, user=None):
    categoria = Category.objects.get_or_create(restaurant=restaurant, name="Mercearia")[0]
    item = Item.objects.create(restaurant=restaurant, name=nome, category=categoria, unit=unidade)
    if stock:
        register_movement(item=item, movement_type=StockMovement.Type.ENTRADA, quantity=stock, user=user)
        item.refresh_from_db()
    return item


def _na_casa(client, user, casa):
    client.force_login(user)
    sessao = client.session
    sessao[SESSION_KEY] = casa.pk
    sessao.save()


class TestIsolamento:
    def test_no_cross_restaurant_leak(self, client, manager, admin_user, casa_b):
        """Um objeto de outra casa dá 404, mesmo com o pk certo, e não aparece
        nas listas."""
        worker = Worker.objects.create(restaurant=casa_b, full_name="Ana da Baixa")
        item = _artigo(casa_b, nome="Feijão da Baixa")
        entrada = open_shift(worker=worker, at=timezone.now() - datetime.timedelta(hours=6))
        tipo = AbsenceType.objects.get(restaurant=casa_b, name="Férias")
        pedido = create_request(
            worker=worker, absence_type=tipo, start_date=datetime.date(2026, 11, 9), end_date=datetime.date(2026, 11, 10)
        )
        correcao = request_correction(
            worker=worker, note="esqueci", check_in=entrada.check_in, check_out=entrada.check_in + datetime.timedelta(hours=4), entry=entrada
        )
        area = WorkArea.objects.filter(restaurant=casa_b).first()
        client.force_login(manager)

        urls = [
            reverse("workers:editar", args=[worker.pk]),
            reverse("workers:codigo", args=[worker.pk]),
            reverse("workers:conta", args=[worker.pk]),
            reverse("inventory:editar", args=[item.pk]),
            reverse("inventory:movimento", args=[item.pk]),
            reverse("inventory:transferir", args=[item.pk]),
            reverse("inventory:categoria_editar", args=[item.category.pk]),
            reverse("attendance:corrigir", args=[entrada.pk]),
            reverse("attendance:acrescentar", args=[worker.pk]),
            reverse("vacations:celula", args=[worker.pk, "2026-11-09"]),
            reverse("shifts:celula", args=[worker.pk, "2026-11-09"]),
        ]
        for url in urls:
            assert client.get(url).status_code == 404, url
        assert client.post(reverse("vacations:decidir", args=[pedido.pk, "aprovar"])).status_code == 404
        assert client.post(reverse("attendance:decidir_pedido", args=[correcao.pk, "aprovar"])).status_code == 404

        for url in [
            reverse("workers:lista"),
            reverse("inventory:lista"),
            reverse("inventory:historico"),
            reverse("vacations:lista"),
            reverse("vacations:calendario") + "?mes=2026-11",
            reverse("attendance:dia"),
            reverse("dashboard:home"),
        ]:
            corpo = client.get(url).content.decode()
            assert "Ana da Baixa" not in corpo and "Feijão da Baixa" not in corpo, url

        # A configuração é do Admin, e também fica na casa dele.
        client.force_login(admin_user)
        assert client.get(reverse("config:editar", args=["areas", area.pk])).status_code == 404
        assert client.post(reverse("config:remover", args=["areas", area.pk])).status_code == 404

    def test_user_without_restaurant_sees_nothing(self, client, restaurant):
        """Antes da Fase 9, um utilizador sem restaurante via tudo."""
        solto = User.objects.create_superuser(email="solto@opero.pt", password="segredo-de-teste-123")
        client.force_login(solto)
        assert client.get(reverse("dashboard:home")).status_code == 403
        assert client.get(reverse("inventory:lista")).status_code == 403
        assert client.get(reverse("workers:lista")).status_code == 403

    def test_kiosk_shows_only_its_restaurant(self, client, restaurant, manager, casa_b):
        nossa = Worker.objects.create(restaurant=restaurant, full_name="Marta Silva")
        alheia = Worker.objects.create(restaurant=casa_b, full_name="Ana da Baixa")
        for w in (nossa, alheia):
            w.set_kiosk_code("2468")
        ativar_tablet(client, manager)
        corpo = client.get(reverse("kiosk:inicio")).content.decode()
        assert "Marta Silva" in corpo and "Ana da Baixa" not in corpo
        assert client.get(reverse("kiosk:codigo", args=[alheia.pk])).status_code == 404

    def test_kiosk_without_restaurant_is_not_activated(self, client, manager):
        from django.core import signing

        from accounts.views import DEVICE_COOKIE

        client.cookies[DEVICE_COOKIE] = signing.dumps({"partilhado": True, "area": None}, salt=DEVICE_COOKIE)
        assert client.get(reverse("kiosk:inicio")).status_code == 403


class TestCasaAtiva:
    def test_switch_restaurant(self, client, manager, casa_b):
        dar_acesso(manager, casa_b, User.Role.MANAGER)
        Worker.objects.create(restaurant=casa_b, full_name="Ana da Baixa")
        client.force_login(manager)
        assert "Ana da Baixa" not in client.get(reverse("workers:lista")).content.decode()

        resp = client.post(reverse("dashboard:mudar_casa"), {"casa": casa_b.pk})
        assert resp.url == reverse("dashboard:home")
        corpo = client.get(reverse("workers:lista")).content.decode()
        assert "Ana da Baixa" in corpo
        assert 'id="casa-ativa"' in corpo  # seletor no rail, porque tem duas casas

    def test_cannot_switch_to_restaurant_without_access(self, client, manager, casa_b):
        client.force_login(manager)
        client.post(reverse("dashboard:mudar_casa"), {"casa": casa_b.pk})
        assert client.session.get(SESSION_KEY) != casa_b.pk

    def test_role_is_per_restaurant(self, client, manager, casa_b):
        dar_acesso(manager, casa_b, User.Role.STAFF)
        _na_casa(client, manager, casa_b)
        assert client.get(reverse("workers:lista")).status_code == 403
        assert client.get(reverse("dashboard:home")).status_code == 403
        _na_casa(client, manager, manager.restaurant)
        assert client.get(reverse("workers:lista")).status_code == 200

    def test_post_from_other_restaurant_tab_rejected(self, client, manager, restaurant, casa_b):
        """O formulário foi aberto na casa A; entretanto, noutro separador,
        a sessão passou para a B. O POST é recusado sem gravar nada."""
        dar_acesso(manager, casa_b, User.Role.MANAGER)
        _na_casa(client, manager, casa_b)
        resp = client.post(reverse("workers:novo"), {"full_name": "Novo Colega", "is_active": "on", "_casa": restaurant.pk})
        assert resp.status_code == 302 and resp.url == reverse("dashboard:home")
        assert not Worker.objects.filter(full_name="Novo Colega").exists()

        resp = client.post(
            reverse("workers:novo"), {"full_name": "Novo Colega"}, HTTP_HX_REQUEST="true", HTTP_X_OPERO_CASA=str(restaurant.pk)
        )
        assert resp.status_code == 409 and resp["HX-Redirect"] == reverse("dashboard:home")
        assert not Worker.objects.filter(full_name="Novo Colega").exists()

        # Da casa certa, grava.
        client.post(reverse("workers:novo"), {"full_name": "Novo Colega", "is_active": "on", "_casa": casa_b.pk})
        assert Worker.objects.get(full_name="Novo Colega").restaurant == casa_b

    def test_post_login_goes_to_restaurant_with_backoffice(self, client, staff_user, casa_b):
        dar_acesso(staff_user, casa_b, User.Role.MANAGER)
        client.force_login(staff_user)
        assert client.get(reverse("accounts:pos_login")).url == reverse("dashboard:home")
        assert client.session[SESSION_KEY] == casa_b.pk


class TestAcessos:
    def test_default_membership_follows_user(self, manager, restaurant):
        assert Membership.objects.get(user=manager, restaurant=restaurant).role == User.Role.MANAGER
        manager.role = User.Role.STOCK
        manager.save()
        assert Membership.objects.get(user=manager, restaurant=restaurant).role == User.Role.STOCK
        assert manager.organization == restaurant.organization

    def test_remove_default_restaurant_moves_default(self, manager, restaurant, casa_b):
        dar_acesso(manager, casa_b, User.Role.STOCK)
        tirar_acesso(manager, restaurant)
        manager.refresh_from_db()
        assert manager.restaurant == casa_b and manager.role == User.Role.STOCK
        assert list(manager.casas()) == [casa_b]

    def test_access_to_other_group_rejected(self, manager):
        alheia = Restaurant.objects.create(name="Outra Casa", slug="outra-casa")
        with pytest.raises(ValidationError):
            dar_acesso(manager, alheia, User.Role.MANAGER)

    def test_group_admin_manages_access(self, client, dono, manager, casa_b):
        client.force_login(dono)
        url = reverse("grupo:acessos", args=[casa_b.pk])
        client.post(url, {"acao": "dar", "user": manager.pk, "role": User.Role.MANAGER})
        assert Membership.objects.get(user=manager, restaurant=casa_b).role == User.Role.MANAGER
        client.post(url, {"acao": "perfil", "user": manager.pk, "role": User.Role.STOCK})
        assert Membership.objects.get(user=manager, restaurant=casa_b).role == User.Role.STOCK
        client.post(url, {"acao": "tirar", "user": manager.pk})
        assert not Membership.objects.filter(user=manager, restaurant=casa_b).exists()

    def test_only_group_admin_sees_group_area(self, client, admin_user, dono):
        client.force_login(admin_user)
        for nome in ["grupo:painel", "grupo:casas", "grupo:nova_casa"]:
            assert client.get(reverse(nome)).status_code == 403
        client.force_login(dono)
        assert client.get(reverse("grupo:painel")).status_code == 200

    def test_group_admin_creates_restaurant(self, client, dono, restaurant):
        client.force_login(dono)
        resp = client.post(reverse("grupo:nova_casa"), {"name": "Tasca do Porto", "nif": "123456780", "is_active": "on"})
        assert "Este NIF não é válido" in resp.content.decode()
        client.post(reverse("grupo:nova_casa"), {"name": "Tasca do Porto", "nif": "123456789", "is_active": "on"})
        nova = Restaurant.objects.get(name="Tasca do Porto")
        assert nova.organization == restaurant.organization and nova.slug == "tasca-do-porto"
        assert WorkArea.objects.filter(restaurant=nova).count() == 3
        assert nova in dono.casas()

    def test_group_panel_shows_each_restaurant(self, client, dono, restaurant, casa_b, manager):
        _artigo(casa_b, nome="Feijão")  # stock 0 com mínimo 0: conta como baixo
        client.force_login(dono)
        linhas = client.get(reverse("grupo:painel")).context["linhas"]
        assert [l["casa"] for l in linhas] == [casa_b, restaurant]
        assert linhas[0]["stock_baixo"] == 1 and linhas[1]["stock_baixo"] == 0

    def test_account_role_change_only_affects_this_restaurant(self, client, manager, staff_user, restaurant, casa_b):
        dar_acesso(staff_user, casa_b, User.Role.STOCK)
        worker = Worker.objects.create(restaurant=restaurant, full_name="Marta Silva", user=staff_user)
        client.force_login(manager)
        client.post(reverse("workers:conta", args=[worker.pk]), {"acao": "perfil", "role": User.Role.STOCK})
        assert Membership.objects.get(user=staff_user, restaurant=restaurant).role == User.Role.STOCK
        assert Membership.objects.get(user=staff_user, restaurant=casa_b).role == User.Role.STOCK
        staff_user.refresh_from_db()
        assert staff_user.role == User.Role.STOCK


class TestTransferencias:
    def test_transfer_moves_stock_between_restaurants(self, manager, restaurant, casa_b):
        origem = _artigo(restaurant, stock=20, user=manager)
        destino = _artigo(casa_b)
        trf = transfer_stock(source_item=origem, destination_item=destino, quantity="5", user=manager)
        origem.refresh_from_db()
        destino.refresh_from_db()
        assert origem.current_stock == Decimal("15") and destino.current_stock == Decimal("5")
        movimentos = StockMovement.objects.filter(transfer=trf)
        assert {m.movement_type for m in movimentos} == {StockMovement.Type.SAIDA, StockMovement.Type.ENTRADA}
        assert all(m.origin == StockMovement.Origin.TRANSFERENCIA and m.reference == f"TRF-{trf.pk}" for m in movimentos)

    def test_transfer_without_stock_changes_nothing(self, manager, restaurant, casa_b):
        origem = _artigo(restaurant, stock=2, user=manager)
        destino = _artigo(casa_b)
        with pytest.raises(ValidationError):
            transfer_stock(source_item=origem, destination_item=destino, quantity="5", user=manager)
        destino.refresh_from_db()
        assert destino.current_stock == 0
        assert not StockMovement.objects.filter(origin=StockMovement.Origin.TRANSFERENCIA).exists()

    def test_transfer_rules(self, manager, restaurant, casa_b):
        origem = _artigo(restaurant, stock=10, user=manager)
        with pytest.raises(ValidationError, match="mesma unidade"):
            transfer_stock(source_item=origem, destination_item=_artigo(casa_b, unidade=Item.Unit.UN), quantity="1", user=manager)
        with pytest.raises(ValidationError, match="mesmo grupo"):
            transfer_stock(
                source_item=origem,
                destination_item=_artigo(Restaurant.objects.create(name="Outra", slug="outra")),
                quantity="1",
                user=manager,
            )
        with pytest.raises(ValidationError, match="outra"):
            transfer_stock(source_item=origem, destination_item=origem, quantity="1", user=manager)

    def test_transfer_view_creates_item_in_destination(self, client, manager, restaurant, casa_b):
        origem = _artigo(restaurant, stock=20, user=manager)
        client.force_login(manager)
        assert "Transferir" in client.get(reverse("inventory:lista")).content.decode()
        resp = client.post(
            reverse("inventory:transferir", args=[origem.pk]),
            {"destino": casa_b.pk, "destination_item": "novo", "quantity": "5", "note": "falta para o jantar"},
        )
        assert resp.status_code == 302
        novo = Item.objects.get(restaurant=casa_b, name="Arroz")
        assert novo.current_stock == Decimal("5") and novo.unit == Item.Unit.KG
        assert novo.category.name == "Mercearia"

    def test_single_restaurant_has_no_transfer(self, client, manager, restaurant):
        origem = _artigo(restaurant, stock=5, user=manager)
        client.force_login(manager)
        assert "Transferir" not in client.get(reverse("inventory:lista")).content.decode()
        assert client.get(reverse("inventory:transferir", args=[origem.pk])).status_code == 302


def test_restaurant_without_group_gets_its_own(db):
    casa = Restaurant.objects.create(name="Casa Sozinha", slug="casa-sozinha")
    assert casa.organization.name == "Casa Sozinha"
    assert Organization.objects.count() == 1
