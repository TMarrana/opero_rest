"""Fase 14: o stock atualizado pelas vendas. Cada produto vendido com ficha
técnica tira do stock os artigos da receita, num movimento por artigo e por
dia de serviço; a mesma venda nunca sai duas vezes, e uma nota de crédito
devolve. Só os movimentos de venda podem deixar o stock negativo. Entre
duas contagens físicas, compara-se o consumo esperado com o real."""
import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from inventory import counts
from inventory.consumption import register_consumption
from inventory.models import Category, InternalConsumption, Item, StockCount, StockMovement
from inventory.services import register_count, register_movement
from recipes import services as fichas
from recipes.models import Recipe
from sales import sintetico, stock
from sales.models import PosProduct, SaleStockMovement, SalesSettings
from sales.services import import_saft
from sales.sintetico import Doc

pytestmark = pytest.mark.django_db
HOJE = timezone.localdate
ONTEM = lambda: HOJE() - datetime.timedelta(days=2)  # noqa: E731 - dois dias, para o dia de serviço já ter acabado


def _artigo(restaurant, nome, unidade, stock_inicial=None, custo=None, user=None):
    categoria = Category.objects.get_or_create(restaurant=restaurant, name="Frescos")[0]
    item = Item.objects.create(
        restaurant=restaurant, name=nome, category=categoria, unit=unidade,
        reference_cost=None if custo is None else Decimal(custo),
    )
    if stock_inicial:
        register_movement(item=item, movement_type=StockMovement.Type.ENTRADA, quantity=stock_inicial, user=user)
        item.refresh_from_db()
    return item


@pytest.fixture
def casa(restaurant):
    restaurant.nif = "509123457"
    restaurant.save()
    return restaurant


@pytest.fixture
def artigos(casa, manager):
    return {
        "bife": _artigo(casa, "Bife da vazia", Item.Unit.KG, "10", "12.00", manager),
        "ovo": _artigo(casa, "Ovo", Item.Unit.UN, "60", "0.20", manager),
        "batata": _artigo(casa, "Batata", Item.Unit.KG, "20", "0.80", manager),
    }


@pytest.fixture
def bitoque(casa, manager, artigos):
    receita = fichas.create_recipe(
        organization=casa.organization, name="Bitoque", kind=Recipe.Kind.PRATO, user=manager,
        valid_from=HOJE() - datetime.timedelta(days=30),
        lines=[
            (("Bife da vazia", "KG"), Decimal("0.180"), None),
            (("Ovo", "UN"), Decimal(1), None),
            (("Batata", "KG"), Decimal("0.200"), Decimal(20)),
        ],
    )
    produto = PosProduct.objects.create(restaurant=casa, code="P001", description="Bitoque")
    fichas.link_product(recipe=receita, product=produto, user=manager)
    return receita


def _ligar(casa, desde=None):
    regras = SalesSettings.for_restaurant(casa)
    regras.stock_enabled = True
    regras.stock_from = desde or HOJE() - datetime.timedelta(days=30)
    regras.save()


def _hora(dia, h=13):
    return datetime.datetime.combine(dia, datetime.time(h))


def _importar(casa, user, docs, dia=None):
    dia = dia or ONTEM()
    conteudo = sintetico.gerar(nif=casa.nif, documentos=docs, inicio=dia, fim=dia)
    return import_saft(restaurant=casa, upload=SimpleUploadedFile("saft.xml", conteudo), user=user)


def _bitoques(n, numero="FS E/1", dia=None, **kwargs):
    return Doc(numero, _hora(dia or ONTEM()), [("P001", "Bitoque", n, Decimal("8.94"), Decimal("13"))], **kwargs)


def _stock(item):
    item.refresh_from_db()
    return item.current_stock


class TestAceitacao:
    def test_quarenta_bitoques(self, casa, manager, artigos, bitoque):
        """Importa-se um dia com 40 bitoques: o bife desce 40 × 180 g num só
        movimento com a referência da importação. O mesmo ficheiro outra vez
        não mexe no stock. Uma nota de crédito de 2 bitoques devolve 360 g."""
        _ligar(casa)
        importacao = _importar(casa, manager, [_bitoques(40)])
        bife = artigos["bife"]
        assert _stock(bife) == Decimal("10") - Decimal("7.2")
        saidas = StockMovement.objects.filter(item=bife, origin=StockMovement.Origin.VENDA)
        assert saidas.count() == 1
        assert saidas.get().quantity == Decimal("7.200")
        assert saidas.get().reference == f"SAF-T {importacao.pk}"

        with pytest.raises(ValidationError, match="já foi importado"):
            _importar(casa, manager, [_bitoques(40)])
        assert _stock(bife) == Decimal("2.8")

        _importar(casa, manager, [_bitoques(40), _bitoques(2, numero="NC E/1", tipo="NC")])
        assert _stock(bife) == Decimal("2.8") + Decimal("0.36")
        devolucao = StockMovement.objects.filter(item=bife, origin=StockMovement.Origin.VENDA).latest("pk")
        assert devolucao.movement_type == StockMovement.Type.ENTRADA and devolucao.quantity == Decimal("0.360")


class TestAplicacao:
    def test_waste_counts_in_gross_quantity(self, casa, manager, artigos, bitoque):
        """Com 20 % de quebra, 200 g limpos de batata tiram 250 g do stock."""
        _ligar(casa)
        _importar(casa, manager, [_bitoques(4)])
        assert _stock(artigos["batata"]) == Decimal("19")
        assert _stock(artigos["ovo"]) == Decimal("56")

    def test_disabled_does_nothing(self, casa, manager, artigos, bitoque):
        _importar(casa, manager, [_bitoques(4)])
        assert not StockMovement.objects.filter(origin=StockMovement.Origin.VENDA).exists()

    def test_days_before_start_are_ignored(self, casa, manager, artigos, bitoque):
        _ligar(casa, desde=HOJE())
        _importar(casa, manager, [_bitoques(4)])
        assert _stock(artigos["bife"]) == Decimal("10")

    def test_annulled_later_returns_stock(self, casa, manager, artigos, bitoque):
        _ligar(casa)
        _importar(casa, manager, [_bitoques(10)])
        _importar(casa, manager, [_bitoques(10, estado="A")])
        assert _stock(artigos["bife"]) == Decimal("10")
        assert SaleStockMovement.objects.filter(item=artigos["bife"]).count() == 2

    def test_one_movement_per_item_and_day(self, casa, manager, artigos, bitoque):
        _ligar(casa)
        _importar(casa, manager, [_bitoques(3, numero="FS E/1"), _bitoques(5, numero="FS E/2")])
        assert StockMovement.objects.filter(item=artigos["bife"], origin=StockMovement.Origin.VENDA).count() == 1
        assert _stock(artigos["bife"]) == Decimal("10") - Decimal("1.44")

    def test_sales_can_take_stock_below_zero(self, casa, manager, artigos, bitoque):
        """Uma venda que já aconteceu não se recusa: o stock fica negativo e
        o artigo assinalado para contar."""
        _ligar(casa)
        _importar(casa, manager, [_bitoques(100)])
        bife = artigos["bife"]
        assert _stock(bife) == Decimal("-8")
        assert bife.needs_count
        with pytest.raises(ValidationError, match="deixaria o stock"):
            register_movement(item=bife, movement_type=StockMovement.Type.SAIDA, quantity=1, user=manager)

    def test_product_without_recipe_does_not_move_stock(self, casa, manager, artigos, bitoque):
        _ligar(casa)
        doc = Doc("FS E/1", _hora(ONTEM()), [("C001", "Café", 3, Decimal("0.70"), Decimal("23"))])
        importacao = _importar(casa, manager, [doc])
        resumo = stock.summary(importacao.stock_results)
        assert resumo["movimentos"] == 0
        assert [p.kind for p in resumo["problemas"]] == ["sem_ficha"]
        assert resumo["problemas"][0].quantity == 3

    def test_line_without_item_in_this_house_is_a_problem(self, casa, manager, artigos, bitoque):
        """Catálogo por casa: a linha liga-se pelo nome e pela unidade. Sem o
        artigo nesta casa, não tira nada e fica assinalada."""
        fichas.save_version(
            recipe=bitoque, portions=1, notes="", user=manager, valid_from=HOJE() - datetime.timedelta(days=20),
            lines=[(("Bife da vazia", "KG"), Decimal("0.180"), None), (("Sal grosso", "KG"), Decimal("0.005"), None)],
        )
        _ligar(casa)
        importacao = _importar(casa, manager, [_bitoques(2)])
        problemas = stock.summary(importacao.stock_results)["problemas"]
        assert [(p.kind, p.item_name, p.quantity) for p in problemas] == [("sem_artigo", "Sal grosso", Decimal("0.010"))]
        assert _stock(artigos["bife"]) == Decimal("9.64")

    def test_preparation_expands_into_items(self, casa, manager, artigos, bitoque):
        """Um molho de 10 doses com 1 l de natas: cada bitoque com uma dose
        de molho tira 0,1 l."""
        natas = _artigo(casa, "Natas", Item.Unit.L, "5", user=manager)
        molho = fichas.create_recipe(
            organization=casa.organization, name="Molho", kind=Recipe.Kind.PREPARACAO, user=manager, portions=10,
            valid_from=HOJE() - datetime.timedelta(days=30), lines=[(("Natas", "L"), Decimal(1), None)],
        )
        fichas.save_version(
            recipe=bitoque, portions=1, notes="", user=manager, valid_from=HOJE() - datetime.timedelta(days=20),
            lines=[(("Bife da vazia", "KG"), Decimal("0.180"), None), (molho, Decimal(1), None)],
        )
        _ligar(casa)
        _importar(casa, manager, [_bitoques(5)])
        assert _stock(natas) == Decimal("4.5")
        assert _stock(artigos["ovo"]) == Decimal("60")

    def test_version_in_force_on_the_day(self, casa, manager, artigos, bitoque):
        """Uma versão nova vale a partir do seu dia: as vendas de antes usam
        a antiga."""
        fichas.save_version(
            recipe=bitoque, portions=1, notes="", user=manager, valid_from=HOJE() - datetime.timedelta(days=1),
            lines=[(("Bife da vazia", "KG"), Decimal("0.200"), None)],
        )
        _ligar(casa)
        _importar(casa, manager, [_bitoques(10)])
        assert _stock(artigos["bife"]) == Decimal("8.2")

    def test_enabling_applies_days_already_imported(self, client, casa, admin_user, artigos, bitoque):
        _importar(casa, admin_user, [_bitoques(10)])
        assert _stock(artigos["bife"]) == Decimal("10")
        client.force_login(admin_user)
        r = client.post(
            reverse("sales:regras"),
            {"day_cutoff_hour": 5, "service_change_hour": 17, "series": "", "hourly_cost": "", "stock_enabled": "on",
             "stock_from": (HOJE() - datetime.timedelta(days=7)).isoformat()},
        )
        assert r.status_code == 302
        assert _stock(artigos["bife"]) == Decimal("8.2")
        # Guardar outra vez sem mudar nada não volta a tirar.
        client.post(
            reverse("sales:regras"),
            {"day_cutoff_hour": 5, "service_change_hour": 17, "series": "", "hourly_cost": "", "stock_enabled": "on",
             "stock_from": (HOJE() - datetime.timedelta(days=7)).isoformat()},
        )
        assert _stock(artigos["bife"]) == Decimal("8.2")

    def test_enabling_needs_a_start_day(self, client, casa, admin_user):
        client.force_login(admin_user)
        r = client.post(reverse("sales:regras"), {"day_cutoff_hour": 5, "stock_enabled": "on", "stock_from": ""})
        assert r.status_code == 400
        assert not SalesSettings.for_restaurant(casa).stock_enabled

    def test_recipe_fixed_later_is_applied_on_request(self, client, casa, manager, artigos, bitoque):
        """Um produto vendido sem ficha: criada a ficha, «Acertar o stock»
        tira o que faltava; repetir não muda nada."""
        _ligar(casa)
        _importar(casa, manager, [Doc("FS E/1", _hora(ONTEM()), [("B001", "Bife à casa", 5, Decimal("12"), Decimal("13"))])])
        assert _stock(artigos["bife"]) == Decimal("10")
        receita = fichas.create_recipe(
            organization=casa.organization, name="Bife à casa", kind=Recipe.Kind.PRATO, user=manager,
            valid_from=HOJE() - datetime.timedelta(days=30), lines=[(("Bife da vazia", "KG"), Decimal("0.250"), None)],
        )
        fichas.link_product(recipe=receita, product=PosProduct.objects.get(code="B001"), user=manager)
        client.force_login(manager)
        client.post(reverse("sales:stock"))
        assert _stock(artigos["bife"]) == Decimal("8.75")
        client.post(reverse("sales:stock"))
        assert _stock(artigos["bife"]) == Decimal("8.75")

    def test_stock_page(self, client, casa, manager, artigos, bitoque):
        _ligar(casa)
        _importar(casa, manager, [_bitoques(2), Doc("FS E/2", _hora(ONTEM()), [("C001", "Café", 3, Decimal("0.70"), Decimal("23"))])])
        client.force_login(manager)
        corpo = client.get(reverse("sales:stock")).content.decode()
        assert "Café não tem ficha técnica" in corpo
        assert ONTEM().strftime("%d/%m/%Y") in corpo


class TestContagens:
    def test_count_adjusts_and_is_kept(self, casa, manager, artigos):
        bife = artigos["bife"]
        contagem = register_count(item=bife, counted=Decimal("9.5"), user=manager)
        assert _stock(bife) == Decimal("9.5")
        assert contagem.expected_quantity == Decimal("10") and contagem.difference == Decimal("-0.5")
        assert contagem.movement.origin == StockMovement.Origin.CONTAGEM

    def test_count_fixes_negative_stock(self, casa, manager, artigos, bitoque):
        _ligar(casa)
        _importar(casa, manager, [_bitoques(100)])
        register_count(item=artigos["bife"], counted=Decimal("1"), user=manager)
        assert _stock(artigos["bife"]) == Decimal("1")
        assert not artigos["bife"].needs_count

    def test_equal_count_has_no_movement(self, casa, manager, artigos):
        contagem = register_count(item=artigos["ovo"], counted=Decimal("60"), user=manager)
        assert contagem.movement is None

    def test_theoretical_against_real(self, casa, manager, artigos, bitoque):
        """Entre duas contagens: 10 bitoques (1,8 kg), um consumo interno de
        0,2 kg e uma quebra de 0,5 kg. Na contagem faltam mais 0,3 kg."""
        bife = artigos["bife"]
        agora = timezone.now()
        primeira = register_count(item=bife, counted=Decimal("10"), user=manager, at=agora - datetime.timedelta(days=5))
        _ligar(casa)
        _importar(casa, manager, [_bitoques(10)])
        register_consumption(
            restaurant=casa, worker=None, reason=InternalConsumption.Reason.PROVA, day=HOJE(),
            lines=[(bife, Decimal("0.2"))], user=manager,
        )
        register_movement(item=bife, movement_type=StockMovement.Type.SAIDA, quantity=Decimal("0.5"), user=manager, reason="Caiu ao chão")
        segunda = register_count(item=bife, counted=Decimal("7.2"), user=manager)
        comparacao = counts.compare(segunda)
        assert comparacao.previous == primeira
        assert comparacao.sales == Decimal("1.8")
        assert comparacao.consumption == Decimal("0.2")
        assert comparacao.waste == Decimal("0.5")
        assert comparacao.expected == Decimal("2.5")
        assert comparacao.difference == Decimal("-0.3")
        assert comparacao.real == Decimal("2.8")
        assert comparacao.deviation_pct == Decimal("12.0")
        assert comparacao.value == Decimal("-3.60")

    def test_count_sheet(self, client, casa, stock_user, artigos):
        client.force_login(stock_user)
        assert client.get(reverse("inventory:contagem")).status_code == 200
        r = client.post(
            reverse("inventory:contagem"),
            {f"contado_{artigos['bife'].pk}": "9,5", f"contado_{artigos['ovo'].pk}": "", f"contado_{artigos['batata'].pk}": "20"},
        )
        assert r.status_code == 302
        assert StockCount.objects.count() == 2
        assert _stock(artigos["bife"]) == Decimal("9.5")
        corpo = client.get(reverse("inventory:contagens")).content.decode()
        assert "Bife da vazia" in corpo and "Primeira contagem" in corpo

    def test_count_sheet_rejects_negative_and_saves_nothing(self, client, casa, stock_user, artigos):
        client.force_login(stock_user)
        r = client.post(
            reverse("inventory:contagem"),
            {f"contado_{artigos['bife'].pk}": "9", f"contado_{artigos['ovo'].pk}": "-1"},
        )
        assert r.status_code == 400
        assert not StockCount.objects.exists()
        assert _stock(artigos["bife"]) == Decimal("10")

    def test_count_of_another_house_is_ignored(self, client, casa, stock_user, artigos):
        from core.models import Restaurant

        outra = Restaurant.objects.create(organization=casa.organization, name="Outra", slug="outra")
        alheio = _artigo(outra, "Bife da vazia", Item.Unit.KG)
        client.force_login(stock_user)
        client.post(reverse("inventory:contagem"), {f"contado_{alheio.pk}": "3", f"contado_{artigos['bife'].pk}": "9"})
        assert not StockCount.objects.filter(item=alheio).exists()

    def test_stock_list_flags_negative(self, client, casa, manager, artigos, bitoque):
        _ligar(casa)
        _importar(casa, manager, [_bitoques(100)])
        client.force_login(manager)
        corpo = client.get(reverse("inventory:lista")).content.decode()
        assert "Stock negativo, contar" in corpo
        assert "com stock negativo, por contar" in corpo
