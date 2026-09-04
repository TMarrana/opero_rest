"""Fase 1: invariantes de stock (secção 11) e fluxo ponta a ponta."""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from inventory.models import Category, Item, StockMovement
from inventory.services import register_movement

pytestmark = pytest.mark.django_db


@pytest.fixture
def categoria(restaurant):
    return Category.objects.create(restaurant=restaurant, name="Frescos de teste")


@pytest.fixture
def item(restaurant, categoria):
    return Item.objects.create(
        restaurant=restaurant,
        name="Tomate chucha",
        category=categoria,
        unit=Item.Unit.KG,
        minimum_stock=Decimal("10"),
    )


def _movimento(item, user, tipo=StockMovement.Type.ENTRADA, qtd="5"):
    return register_movement(item=item, movement_type=tipo, quantity=Decimal(qtd), user=user)


class TestRegisterMovement:
    def test_entrada_aumenta_e_saida_diminui(self, item, stock_user):
        _movimento(item, stock_user, qtd="20")
        item.refresh_from_db()
        assert item.current_stock == Decimal("20")
        _movimento(item, stock_user, StockMovement.Type.SAIDA, "7.5")
        item.refresh_from_db()
        assert item.current_stock == Decimal("12.5")

    def test_ajustes(self, item, stock_user):
        _movimento(item, stock_user, StockMovement.Type.AJUSTE_POS, "3")
        _movimento(item, stock_user, StockMovement.Type.AJUSTE_NEG, "1")
        item.refresh_from_db()
        assert item.current_stock == Decimal("2")

    def test_quantidade_nao_positiva_rejeitada(self, item, stock_user):
        with pytest.raises(ValidationError):
            _movimento(item, stock_user, qtd="0")
        with pytest.raises(ValidationError):
            _movimento(item, stock_user, qtd="-4")

    def test_stock_nao_fica_negativo(self, item, stock_user):
        _movimento(item, stock_user, qtd="5")
        with pytest.raises(ValidationError):
            _movimento(item, stock_user, StockMovement.Type.SAIDA, "6")
        item.refresh_from_db()
        assert item.current_stock == Decimal("5")
        assert item.movements.count() == 1  # o movimento inválido não ficou gravado

    def test_movimento_guarda_autor_e_datas(self, item, stock_user):
        """Invariante 5: cada registo guarda data, hora e utilizador."""
        mov = _movimento(item, stock_user)
        assert mov.created_by == stock_user
        assert mov.occurred_at is not None
        assert mov.created_at is not None


class TestStockOnlyChangesViaMovement:
    def test_stock_only_changes_via_movement(self, client, item, stock_user):
        """Invariante 1: nenhuma view escreve current_stock. Editar o artigo
        com um current_stock injetado no POST não altera o stock."""
        _movimento(item, stock_user, qtd="20")
        client.force_login(stock_user)
        resp = client.post(
            reverse("inventory:editar", args=[item.pk]),
            {
                "name": item.name,
                "category": item.category_id,
                "unit": item.unit,
                "minimum_stock": "10",
                "reference_cost": "",
                "is_active": "on",
                "notes": "",
                "current_stock": "999",  # tentativa de escrita direta
            },
        )
        assert resp.status_code == 302
        item.refresh_from_db()
        assert item.current_stock == Decimal("20")

    def test_form_de_artigo_nao_expoe_current_stock(self):
        from inventory.forms import ItemForm

        assert "current_stock" not in ItemForm().fields


class TestMovementCannotBeDeleted:
    def test_movement_cannot_be_deleted(self, item, stock_user):
        """Invariante 2: sem caminho de delete na UI nem no admin."""
        from django.contrib.admin.sites import site
        from django.urls import NoReverseMatch

        _movimento(item, stock_user)
        admin_instance = site._registry[StockMovement]
        assert admin_instance.has_delete_permission(request=None) is False
        assert admin_instance.has_change_permission(request=None) is False
        assert admin_instance.has_add_permission(request=None) is False
        # Não existe URL de delete no módulo de stock.
        with pytest.raises(NoReverseMatch):
            reverse("inventory:movimento_eliminar", args=[1])


class TestPermissoes:
    def test_staff_cannot_edit_items(self, client, staff_user, item):
        client.force_login(staff_user)
        urls = [
            reverse("inventory:lista"),
            reverse("inventory:novo"),
            reverse("inventory:editar", args=[item.pk]),
            reverse("inventory:movimento", args=[item.pk]),
            reverse("inventory:historico"),
            reverse("inventory:categorias"),
        ]
        for url in urls:
            assert client.get(url).status_code == 403, url

    def test_gerente_e_stock_acedem(self, client, manager, stock_user):
        for user in [manager, stock_user]:
            client.force_login(user)
            assert client.get(reverse("inventory:lista")).status_code == 200


class TestFluxoHTMX:
    def test_registo_de_movimento_via_post(self, client, item, stock_user):
        """Aceitação da Fase 1: criar artigo, registar entrada, stock
        atualizado e movimento no histórico."""
        client.force_login(stock_user)
        resp = client.post(
            reverse("inventory:movimento", args=[item.pk]),
            {
                "movement_type": "ENTRADA",
                "quantity": "12.5",
                "occurred_at": "2026-09-04T10:00",
                "reason": "receção do fornecedor",
                "reference": "guia 4412",
            },
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200
        assert "HX-Trigger" in resp
        item.refresh_from_db()
        assert item.current_stock == Decimal("12.5")
        mov = item.movements.get()
        assert mov.created_by == stock_user
        assert mov.reference == "guia 4412"
        # O histórico mostra o movimento.
        resp = client.get(reverse("inventory:historico"))
        assert "Tomate chucha" in resp.content.decode()

    def test_saida_excessiva_devolve_erro_no_modal(self, client, item, stock_user):
        client.force_login(stock_user)
        resp = client.post(
            reverse("inventory:movimento", args=[item.pk]),
            {"movement_type": "SAIDA", "quantity": "5", "occurred_at": "2026-09-04T10:00"},
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200
        assert resp["HX-Retarget"] == "#modal-slot"
        assert "deixaria o stock" in resp.content.decode()
        item.refresh_from_db()
        assert item.current_stock == 0

    def test_filtro_stock_baixo(self, client, restaurant, categoria, stock_user):
        cheio = Item.objects.create(
            restaurant=restaurant, name="Cheio", category=categoria, minimum_stock=1
        )
        register_movement(item=cheio, movement_type="ENTRADA", quantity=Decimal("50"), user=stock_user)
        Item.objects.create(restaurant=restaurant, name="Vazio", category=categoria, minimum_stock=1)
        client.force_login(stock_user)
        corpo = client.get(reverse("inventory:lista"), {"baixo": "1"}).content.decode()
        assert "Vazio" in corpo
        assert "Cheio" not in corpo


class TestCategorias:
    def test_sementes_criadas_com_restaurante(self, restaurant):
        nomes = set(restaurant.categories.values_list("name", flat=True))
        assert {"Bebidas", "Mercearia", "Frescos", "Limpeza", "Embalagem"} <= nomes

    def test_categoria_com_artigos_nao_se_elimina(self, client, item, categoria, manager):
        client.force_login(manager)
        resp = client.post(reverse("inventory:categoria_eliminar", args=[categoria.pk]), follow=True)
        assert Category.objects.filter(pk=categoria.pk).exists()
        assert "tem artigos associados" in resp.content.decode()

    def test_renomear_categoria(self, client, categoria, manager):
        client.force_login(manager)
        resp = client.post(
            reverse("inventory:categoria_editar", args=[categoria.pk]), {"name": "Hortofruticolas"}
        )
        assert resp.status_code == 302
        categoria.refresh_from_db()
        assert categoria.name == "Hortofruticolas"
