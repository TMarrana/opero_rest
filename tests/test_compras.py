"""Fase 11: fornecedores e compras. A receção dá entrada no stock pelo
register_movement(), atualiza o custo e nunca se apaga."""
import datetime
from decimal import Decimal

import pytest
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from core.models import Organization, Restaurant
from inventory.models import Category, Item, StockMovement
from inventory.services import register_movement
from purchasing import services
from purchasing.models import PurchaseOrder, Receipt, ReceiptLine, Supplier, SupplierItem

pytestmark = pytest.mark.django_db
HOJE = timezone.localdate


def _artigo(restaurant, nome, minimo, stock, user, unidade=Item.Unit.KG):
    categoria = Category.objects.get_or_create(restaurant=restaurant, name="Frescos")[0]
    item = Item.objects.create(
        restaurant=restaurant, name=nome, category=categoria, unit=unidade, minimum_stock=Decimal(minimo)
    )
    if Decimal(stock):
        register_movement(item=item, movement_type=StockMovement.Type.ENTRADA, quantity=Decimal(stock), user=user)
        item.refresh_from_db()
    return item


@pytest.fixture
def frescos(restaurant):
    return Supplier.objects.create(organization=restaurant.organization, name="Frescos do Mercado", delivery_days="1,4")


@pytest.fixture
def mercearia(restaurant):
    return Supplier.objects.create(organization=restaurant.organization, name="Mercearia Central")


@pytest.fixture
def artigos(restaurant, stock_user, frescos, mercearia):
    tomate = _artigo(restaurant, "Tomate", "10", "2", stock_user)
    alface = _artigo(restaurant, "Alface", "5", "1", stock_user)
    cebola = _artigo(restaurant, "Cebola", "8", "3", stock_user)
    arroz = _artigo(restaurant, "Arroz", "10", "4", stock_user)
    _artigo(restaurant, "Sal", "1", "5", stock_user)  # acima do mínimo
    for item, preco in ((tomate, "1.20"), (alface, "0.80"), (cebola, "0.65")):
        services.save_supplier_item(supplier=frescos, item=item, last_price=Decimal(preco), preferred=True)
    services.save_supplier_item(supplier=mercearia, item=arroz, supplier_ref="ARZ-5", last_price=Decimal("1.10"), preferred=True)
    return {"tomate": tomate, "alface": alface, "cebola": cebola, "arroz": arroz}


def _enviada(restaurant, supplier, user, linhas):
    encomenda = services.create_order(restaurant=restaurant, supplier=supplier, lines=linhas, user=user)
    return services.send_order(order=encomenda, user=user)


class TestListaDeCompras:
    def test_agrupa_pelo_preferido_e_sugere_repor_o_minimo(self, restaurant, artigos, frescos, mercearia, stock_user):
        _artigo(restaurant, "Lixívia", "2", "0", stock_user, unidade=Item.Unit.L)
        grupos = services.shopping_list(restaurant)
        assert [g[0] for g in grupos] == [frescos, mercearia, None]
        tomate = next(l for l in grupos[0][1] if l["item"] == artigos["tomate"])
        assert tomate["sugerido"] == Decimal(8) and tomate["preco"] == Decimal("1.20")
        assert [l["item"].name for l in grupos[2][1]] == ["Lixívia"]
        assert all(l["item"].name != "Sal" for _, linhas in grupos for l in linhas)

    def test_desconta_o_que_ja_esta_encomendado(self, restaurant, artigos, frescos, stock_user):
        _enviada(restaurant, frescos, stock_user, [(artigos["tomate"], Decimal(5), None)])
        grupos = dict(services.shopping_list(restaurant))
        tomate = next(l for l in grupos[frescos] if l["item"] == artigos["tomate"])
        assert (tomate["encomendado"], tomate["sugerido"]) == (Decimal(5), Decimal(3))

    def test_so_um_preferido_por_artigo(self, artigos, mercearia, frescos):
        services.save_supplier_item(supplier=mercearia, item=artigos["tomate"], preferred=True)
        assert SupplierItem.objects.get(supplier=frescos, item=artigos["tomate"]).preferred is False
        assert SupplierItem.objects.get(supplier=mercearia, item=artigos["tomate"]).preferred is True


class TestEncomendas:
    def test_rascunho_muda_e_depois_de_enviada_nao(self, restaurant, artigos, frescos, stock_user):
        encomenda = services.create_order(
            restaurant=restaurant, supplier=frescos, lines=[(artigos["tomate"], Decimal(8), None)], user=stock_user
        )
        assert encomenda.state == PurchaseOrder.State.RASCUNHO
        assert encomenda.lines.get().unit_price == Decimal("1.20")  # último preço do fornecedor
        services.update_draft(
            order=encomenda, lines={artigos["tomate"]: (0, None), artigos["alface"]: (Decimal(4), Decimal("0.75"))}
        )
        assert [l.item for l in encomenda.lines.all()] == [artigos["alface"]]
        services.send_order(order=encomenda, user=stock_user)
        with pytest.raises(ValidationError, match="enviada"):
            services.update_draft(order=encomenda, lines={artigos["tomate"]: (Decimal(1), None)})

    def test_encomenda_vazia_nao_se_envia(self, restaurant, frescos, stock_user):
        encomenda = services.create_order(restaurant=restaurant, supplier=frescos, lines=[], user=stock_user)
        with pytest.raises(ValidationError, match="não tem linhas"):
            services.send_order(order=encomenda, user=stock_user)

    def test_fornecedor_arquivado_nao_recebe_encomendas(self, restaurant, artigos, frescos, stock_user):
        frescos.is_active = False
        frescos.save()
        with pytest.raises(ValidationError, match="arquivado"):
            services.create_order(restaurant=restaurant, supplier=frescos, lines=[], user=stock_user)

    def test_texto_da_encomenda(self, restaurant, artigos, mercearia, stock_user):
        encomenda = services.create_order(
            restaurant=restaurant, supplier=mercearia, lines=[(artigos["arroz"], Decimal("7.5"), None)], user=stock_user
        )
        texto = services.order_text(encomenda)
        assert encomenda.reference in texto
        assert "- 7,5 kg · Arroz (ref. ARZ-5)" in texto

    def test_cancelar(self, restaurant, artigos, frescos, stock_user):
        encomenda = _enviada(restaurant, frescos, stock_user, [(artigos["tomate"], Decimal(8), None)])
        services.cancel_order(order=encomenda, user=stock_user)
        assert encomenda.__class__.objects.get(pk=encomenda.pk).state == PurchaseOrder.State.CANCELADA
        linha = encomenda.lines.get()
        with pytest.raises(ValidationError, match="cancelada"):
            services.receive(
                restaurant=restaurant, supplier=frescos, order=encomenda, user=stock_user,
                document_number="G 1", document_date=HOJE(), lines=[(linha.item, Decimal(1), None, linha)],
            )


class TestRececao:
    def test_receipt_creates_entry_movement(self, restaurant, artigos, frescos, stock_user):
        encomenda = _enviada(restaurant, frescos, stock_user, [(artigos["tomate"], Decimal(8), Decimal("1.20"))])
        linha = encomenda.lines.get()
        rececao = services.receive(
            restaurant=restaurant, supplier=frescos, order=encomenda, user=stock_user,
            document_number="FT 2026/77", document_date=HOJE(), lines=[(artigos["tomate"], Decimal(8), Decimal("1.35"), linha)],
        )
        mov = rececao.lines.get().movement
        assert (mov.movement_type, mov.origin, mov.quantity) == (StockMovement.Type.ENTRADA, StockMovement.Origin.COMPRA, Decimal(8))
        assert mov.reference == f"{encomenda.reference} · FT 2026/77"
        assert mov.created_by == stock_user
        tomate = Item.objects.get(pk=artigos["tomate"].pk)
        assert tomate.current_stock == Decimal(10)
        assert tomate.reference_cost == Decimal("1.35")
        si = SupplierItem.objects.get(supplier=frescos, item=tomate)
        assert (si.last_price, si.last_price_at) == (Decimal("1.35"), HOJE())
        assert PurchaseOrder.objects.get(pk=encomenda.pk).state == PurchaseOrder.State.RECEBIDA

    def test_aceitacao_lista_encomenda_e_rececao_com_uma_linha_a_menos(self, client, restaurant, artigos, frescos, stock_user):
        """Critério de aceitação da Fase 11."""
        client.force_login(stock_user)
        assert client.get(reverse("purchasing:lista")).status_code == 200
        resp = client.post(
            reverse("purchasing:lista"),
            {"fornecedor": frescos.pk, f"qtd-{artigos['tomate'].pk}": "8", f"qtd-{artigos['alface'].pk}": "4",
             f"qtd-{artigos['cebola'].pk}": "5"},
        )
        encomenda = PurchaseOrder.objects.get()
        assert resp.url == reverse("purchasing:encomenda", args=[encomenda.pk])
        assert encomenda.lines.count() == 3
        client.post(reverse("purchasing:encomenda", args=[encomenda.pk]), {
            "acao": "enviar", f"qtd-{artigos['tomate'].pk}": "8", f"preco-{artigos['tomate'].pk}": "1,20",
            f"qtd-{artigos['alface'].pk}": "4", f"preco-{artigos['alface'].pk}": "0,80",
            f"qtd-{artigos['cebola'].pk}": "5", f"preco-{artigos['cebola'].pk}": "0,65",
        })
        encomenda.refresh_from_db()
        assert encomenda.state == PurchaseOrder.State.ENVIADA
        assert client.get(reverse("purchasing:receber", args=[encomenda.pk])).status_code == 200
        linhas = {l.item_id: l for l in encomenda.lines.all()}
        dados = {"document_number": "GR 123", "document_date": HOJE().isoformat()}
        dados.update({f"qtd-{linhas[artigos['tomate'].pk].pk}": "8", f"preco-{linhas[artigos['tomate'].pk].pk}": "1,25"})
        dados.update({f"qtd-{linhas[artigos['alface'].pk].pk}": "4", f"preco-{linhas[artigos['alface'].pk].pk}": "0,80"})
        dados.update({f"qtd-{linhas[artigos['cebola'].pk].pk}": "", f"preco-{linhas[artigos['cebola'].pk].pk}": "0,65"})
        resp = client.post(reverse("purchasing:receber", args=[encomenda.pk]), dados)
        assert resp.status_code == 302
        encomenda.refresh_from_db()
        assert encomenda.state == PurchaseOrder.State.PARCIAL
        tomate, cebola = Item.objects.get(pk=artigos["tomate"].pk), Item.objects.get(pk=artigos["cebola"].pk)
        assert (tomate.current_stock, tomate.reference_cost) == (Decimal(10), Decimal("1.25"))
        assert (cebola.current_stock, cebola.reference_cost) == (Decimal(3), None)
        # A cebola que falta continua encomendada na lista de compras.
        grupos = dict(services.shopping_list(restaurant))
        assert next(l for l in grupos[frescos] if l["item"] == cebola)["encomendado"] == Decimal(5)
        # A segunda receção completa a encomenda.
        services.receive(
            restaurant=restaurant, supplier=frescos, order=encomenda, user=stock_user, document_number="GR 124",
            document_date=HOJE(), lines=[(cebola, Decimal(5), Decimal("0.65"), linhas[cebola.pk])],
        )
        assert PurchaseOrder.objects.get(pk=encomenda.pk).state == PurchaseOrder.State.RECEBIDA

    def test_rececao_sem_encomenda(self, client, restaurant, artigos, mercearia, stock_user):
        client.force_login(stock_user)
        url = reverse("purchasing:rececao_nova")
        assert client.get(url, {"fornecedor": mercearia.pk}).status_code == 200
        resp = client.post(url, {
            "fornecedor": mercearia.pk, "document_number": "FT 9", "document_date": HOJE().isoformat(),
            "item-0": artigos["arroz"].pk, "qtd-0": "10", "preco-0": "1,05",
            "item-1": artigos["tomate"].pk, "qtd-1": "2", "preco-1": "",
        })
        rececao = Receipt.objects.get()
        assert resp.url == reverse("purchasing:rececao", args=[rececao.pk])
        assert rececao.order is None
        assert Item.objects.get(pk=artigos["arroz"].pk).current_stock == Decimal(14)
        mov = StockMovement.objects.filter(origin=StockMovement.Origin.COMPRA, item=artigos["arroz"]).get()
        assert mov.reference == f"{rececao.reference} · FT 9"
        # Ficou a ligação do tomate a este fornecedor, sem preço e sem mexer no preferido.
        si = SupplierItem.objects.get(supplier=mercearia, item=artigos["tomate"])
        assert si.last_price is None and not si.preferred

    def test_validacoes(self, restaurant, artigos, frescos, mercearia, stock_user, casa_b_item):
        base = dict(restaurant=restaurant, supplier=frescos, user=stock_user, document_number="G 1", document_date=HOJE())
        with pytest.raises(ValidationError, match="número da fatura"):
            services.receive(**{**base, "document_number": " "}, lines=[(artigos["tomate"], Decimal(1), None, None)])
        with pytest.raises(ValidationError, match="futuro"):
            services.receive(**{**base, "document_date": HOJE() + datetime.timedelta(days=1)}, lines=[(artigos["tomate"], Decimal(1), None, None)])
        with pytest.raises(ValidationError, match="Não há nada recebido"):
            services.receive(**base, lines=[(artigos["tomate"], None, None, None)])
        with pytest.raises(ValidationError, match="não é um artigo desta casa"):
            services.receive(**base, lines=[(casa_b_item, Decimal(1), None, None)])
        encomenda = _enviada(restaurant, mercearia, stock_user, [(artigos["arroz"], Decimal(5), None)])
        with pytest.raises(ValidationError, match="outro fornecedor"):
            services.receive(**base, order=encomenda, lines=[(artigos["arroz"], Decimal(1), None, encomenda.lines.get())])
        assert not Receipt.objects.exists()
        assert not StockMovement.objects.filter(origin=StockMovement.Origin.COMPRA).exists()

    def test_rececao_nao_se_apaga(self, rf, admin_user):
        modelo = admin.site._registry[Receipt]
        pedido = rf.get("/")
        pedido.user = admin_user
        assert not modelo.has_delete_permission(pedido)
        assert not modelo.has_change_permission(pedido)
        assert ReceiptLine._meta.get_field("receipt").remote_field.on_delete.__name__ == "PROTECT"

    def test_exportacao_do_mes(self, client, restaurant, artigos, mercearia, stock_user):
        services.receive(
            restaurant=restaurant, supplier=mercearia, user=stock_user, document_number="FT 9", document_date=HOJE(),
            lines=[(artigos["arroz"], Decimal(10), Decimal("1.05"), None)],
        )
        client.force_login(stock_user)
        resp = client.get(reverse("purchasing:rececoes"))
        assert "Mercearia Central" in resp.content.decode() and "10,50 €" in resp.content.decode()
        texto = client.get(reverse("purchasing:rececoes"), {"mes": HOJE().strftime("%Y-%m"), "exportar": "1"}).content.decode("utf-8-sig")
        assert f"{HOJE().isoformat()};Mercearia Central;;FT 9;;REC-" in texto
        assert ";Arroz;10;KG;1,05;10,5" in texto


@pytest.fixture
def casa_b_item(restaurant, stock_user):
    casa_b = Restaurant.objects.create(organization=restaurant.organization, name="Tasca da Baixa", slug="baixa")
    return _artigo(casa_b, "Tomate da Baixa", "1", "0", stock_user)


class TestAcessos:
    def test_colaborador_nao_entra(self, client, staff_user):
        client.force_login(staff_user)
        for nome in ("lista", "encomendas", "rececoes", "fornecedores"):
            assert client.get(reverse(f"purchasing:{nome}")).status_code == 403

    def test_fornecedores_sao_do_grupo(self, client, restaurant, frescos, manager):
        from accounts.services import dar_acesso

        casa_b = Restaurant.objects.create(organization=restaurant.organization, name="Tasca da Baixa", slug="baixa")
        outro_grupo = Supplier.objects.create(organization=Organization.objects.create(name="Outro"), name="Alheio")
        dar_acesso(manager, casa_b, "MANAGER")
        client.force_login(manager)
        sessao = client.session
        sessao["opero_casa"] = casa_b.pk
        sessao.save()
        assert client.get(reverse("purchasing:fornecedor", args=[frescos.pk])).status_code == 200
        assert client.get(reverse("purchasing:fornecedor", args=[outro_grupo.pk])).status_code == 404

    def test_encomenda_de_outra_casa_da_404(self, client, restaurant, frescos, manager, stock_user, casa_b_item):
        encomenda = services.create_order(
            restaurant=casa_b_item.restaurant, supplier=frescos, lines=[(casa_b_item, Decimal(1), None)], user=stock_user
        )
        client.force_login(manager)
        assert client.get(reverse("purchasing:encomenda", args=[encomenda.pk])).status_code == 404
        assert client.get(reverse("purchasing:receber", args=[encomenda.pk])).status_code == 404

    def test_paginas_abrem(self, client, restaurant, artigos, frescos, stock_user):
        encomenda = _enviada(restaurant, frescos, stock_user, [(artigos["tomate"], Decimal(8), None)])
        rascunho = services.create_order(restaurant=restaurant, supplier=frescos, lines=[(artigos["alface"], Decimal(2), None)], user=stock_user)
        rececao = services.receive(
            restaurant=restaurant, supplier=frescos, order=encomenda, user=stock_user, document_number="G 1",
            document_date=HOJE(), lines=[(artigos["tomate"], Decimal(3), Decimal("1.2"), encomenda.lines.get())],
        )
        client.force_login(stock_user)
        for url in [
            reverse("purchasing:encomendas"),
            reverse("purchasing:encomendas") + "?estado=todas",
            reverse("purchasing:encomenda", args=[encomenda.pk]),
            reverse("purchasing:encomenda", args=[rascunho.pk]),
            reverse("purchasing:encomenda_imprimir", args=[encomenda.pk]),
            reverse("purchasing:rececao", args=[rececao.pk]),
            reverse("purchasing:fornecedores") + "?q=fres",
            reverse("purchasing:fornecedor", args=[frescos.pk]),
            reverse("purchasing:fornecedor_novo"),
            reverse("purchasing:fornecedor_editar", args=[frescos.pk]),
            reverse("purchasing:precos", args=[artigos["tomate"].pk]),
            reverse("inventory:historico"),
        ]:
            assert client.get(url).status_code == 200, url


class TestFornecedores:
    def test_criar_e_arquivar_ou_apagar(self, client, restaurant, artigos, stock_user):
        client.force_login(stock_user)
        resp = client.post(reverse("purchasing:fornecedor_novo"), {"name": "Peixaria Lota", "nif": "509123457", "delivery_days": ["1", "3"]})
        peixaria = Supplier.objects.get(name="Peixaria Lota")
        assert resp.url == reverse("purchasing:fornecedor", args=[peixaria.pk])
        assert peixaria.organization == restaurant.organization
        assert peixaria.delivery_days_display() == "Ter, Qui"
        resp = client.post(reverse("purchasing:fornecedor_novo"), {"name": "peixaria lota"})
        assert resp.status_code == 400
        # Sem histórico, apaga-se.
        client.post(reverse("purchasing:fornecedor", args=[peixaria.pk]), {"acao": "apagar"})
        assert not Supplier.objects.filter(pk=peixaria.pk).exists()

    def test_com_encomendas_arquiva_se(self, client, restaurant, artigos, frescos, stock_user):
        services.create_order(restaurant=restaurant, supplier=frescos, lines=[(artigos["tomate"], Decimal(1), None)], user=stock_user)
        client.force_login(stock_user)
        client.post(reverse("purchasing:fornecedor", args=[frescos.pk]), {"acao": "apagar"})
        assert Supplier.objects.filter(pk=frescos.pk).exists()
        client.post(reverse("purchasing:fornecedor", args=[frescos.pk]), {"acao": "arquivar"})
        frescos.refresh_from_db()
        assert not frescos.is_active

    def test_ligar_artigo_pelo_ecra(self, client, restaurant, artigos, mercearia, stock_user):
        client.force_login(stock_user)
        client.post(
            reverse("purchasing:fornecedor", args=[mercearia.pk]),
            {"acao": "ligar", "item": artigos["tomate"].pk, "supplier_ref": "TOM-1", "last_price": "1,15", "preferred": "1"},
        )
        si = SupplierItem.objects.get(supplier=mercearia, item=artigos["tomate"])
        assert (si.supplier_ref, si.last_price, si.preferred) == ("TOM-1", Decimal("1.15"), True)
        assert not SupplierItem.objects.get(supplier__name="Frescos do Mercado", item=artigos["tomate"]).preferred
