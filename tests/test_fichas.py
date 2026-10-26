"""Fase 13: fichas técnicas. São do grupo, com versões; o custo é o de cada
casa, e o food cost usa o preço que vem do SAF-T."""
import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from core.models import Restaurant
from inventory.models import Category, Item
from recipes import services
from recipes.models import Recipe, RecipeProduct, RecipeVersion
from sales import sintetico
from sales.models import PosProduct
from sales.services import import_saft
from sales.sintetico import Doc

pytestmark = pytest.mark.django_db
HOJE = timezone.localdate


def _artigo(restaurant, nome, unidade, custo):
    categoria = Category.objects.get_or_create(restaurant=restaurant, name="Frescos")[0]
    return Item.objects.create(
        restaurant=restaurant,
        name=nome,
        category=categoria,
        unit=unidade,
        reference_cost=None if custo is None else Decimal(custo),
    )


@pytest.fixture
def artigos(restaurant):
    return {
        "bife": _artigo(restaurant, "Bife da vazia", Item.Unit.KG, "12.00"),
        "ovo": _artigo(restaurant, "Ovo", Item.Unit.UN, "0.20"),
        "batata": _artigo(restaurant, "Batata", Item.Unit.KG, "0.80"),
        "arroz": _artigo(restaurant, "Arroz carolino", Item.Unit.KG, "1.10"),
    }


BITOQUE = [
    (("Bife da vazia", "KG"), Decimal("0.180"), None),
    (("Ovo", "UN"), Decimal(1), None),
    (("Batata", "KG"), Decimal("0.200"), Decimal(20)),
    (("Arroz carolino", "KG"), Decimal("0.100"), None),
]


def _bitoque(restaurant, user, **kwargs):
    kwargs.setdefault("lines", BITOQUE)
    return services.create_recipe(organization=restaurant.organization, name="Bitoque", kind=Recipe.Kind.PRATO, user=user, **kwargs)


def _produto(restaurant, code="P001", descricao="Bitoque", preco="8.94"):
    return PosProduct.objects.create(
        restaurant=restaurant, code=code, description=descricao, last_price=Decimal(preco), last_price_at=timezone.now()
    )


class TestAceitacao:
    def test_bitoque_ligado_ao_pos_com_food_cost(self, client, restaurant, manager, artigos):
        """O gerente cria o Bitoque, liga-o ao código do POS e vê o custo por
        dose e o food cost face ao preço que vem do SAF-T."""
        restaurant.nif = "509123457"
        restaurant.save()
        ontem = HOJE() - datetime.timedelta(days=1)
        hora = datetime.datetime.combine(ontem, datetime.time(13))
        conteudo = sintetico.gerar(
            nif=restaurant.nif,
            documentos=[Doc("FS E/1", hora, [("P001", "Bitoque", 2, Decimal("8.94"), Decimal("13"))])],
            inicio=ontem,
            fim=ontem,
        )
        import_saft(restaurant=restaurant, upload=SimpleUploadedFile("saft.xml", conteudo), user=manager)
        produto = PosProduct.objects.get(restaurant=restaurant, code="P001")

        client.force_login(manager)
        linhas = [
            ("a:KG:Bife da vazia", "0,180", ""),
            ("a:UN:Ovo", "1", ""),
            ("a:KG:Batata", "0,2", "20"),
            ("a:KG:Arroz carolino", "0,1", ""),
        ]
        dados = {"nome": "Bitoque", "tipo": "PRATO", "preco": "", "doses": "1", "notas": "Bife na chapa.", "desde": HOJE().isoformat(), "n_linhas": len(linhas)}
        for i, (ing, qtd, quebra) in enumerate(linhas):
            dados.update({f"ing-{i}": ing, f"qtd-{i}": qtd, f"quebra-{i}": quebra})
        r = client.post(reverse("recipes:nova"), dados)
        ficha = Recipe.objects.get(name="Bitoque")
        assert r.status_code == 302 and r.url == reverse("recipes:ficha", args=[ficha.pk])

        r = client.post(reverse("recipes:ficha", args=[ficha.pk]), {"acao": "ligar", "produto": produto.pk})
        assert RecipeProduct.objects.get(product=produto).recipe == ficha

        r = client.get(reverse("recipes:ficha", args=[ficha.pk]))
        # 0,18 × 12 + 1 × 0,20 + 0,25 × 0,80 + 0,1 × 1,10 = 2,67 €; 2,67 / 8,94 = 29,9 %
        assert r.context["custo"].per_dose == Decimal("2.67")
        assert r.context["preco"] == Decimal("8.94") and r.context["produto_preco"] == produto
        assert r.context["food_cost"] == Decimal("29.9")
        assert "29,9 %" in r.content.decode()


class TestCusto:
    def test_quebra_aumenta_a_quantidade_bruta(self):
        assert services.gross_quantity(Decimal("0.2"), Decimal(20)) == Decimal("0.250")
        assert services.gross_quantity(Decimal("0.2"), Decimal(0)) == Decimal("0.2")

    def test_doses_dividem_o_custo(self, restaurant, manager, artigos):
        ficha = services.create_recipe(
            organization=restaurant.organization, name="Arroz para quatro", kind=Recipe.Kind.PREPARACAO, user=manager,
            portions=Decimal(4), lines=[(("Arroz carolino", "KG"), Decimal("0.4"), None)],
        )
        custo = services.recipe_cost(ficha.current_version(), restaurant)
        assert (custo.total, custo.per_dose) == (Decimal("0.44"), Decimal("0.11"))

    def test_artigo_sem_custo_fica_assinalado(self, restaurant, manager, artigos):
        _artigo(restaurant, "Sal", Item.Unit.KG, None)
        ficha = _bitoque(restaurant, manager, lines=BITOQUE + [(("Sal", "KG"), Decimal("0.002"), None)])
        custo = services.recipe_cost(ficha.current_version(), restaurant)
        assert not custo.complete
        assert [(c.line.item_name, c.problem) for c in custo.problems] == [("Sal", "sem custo")]
        assert custo.per_dose == Decimal("2.67")  # o mínimo, sem o sal

    def test_custo_de_cada_casa(self, restaurant, manager, artigos):
        """A ficha é do grupo; noutra casa liga-se aos artigos de lá pelo nome."""
        ribeira = Restaurant.objects.create(name="Ribeira", slug="ribeira", organization=restaurant.organization)
        _artigo(ribeira, "bife da vazia", Item.Unit.KG, "14.00")
        _artigo(ribeira, "Ovo", Item.Unit.CX, "3.00")
        ficha = _bitoque(restaurant, manager)
        custo = services.recipe_cost(ficha.current_version(), ribeira)
        problemas = {c.line.item_name: c.problem for c in custo.lines}
        assert problemas == {
            "Bife da vazia": "",
            "Ovo": "nesta casa está em CX",
            "Batata": "não há este artigo nesta casa",
            "Arroz carolino": "não há este artigo nesta casa",
        }
        assert custo.lines[0].cost == Decimal("2.52")

    def test_preparacao_entra_pelo_custo_por_dose(self, restaurant, manager, artigos):
        _artigo(restaurant, "Natas", Item.Unit.L, "4.00")
        molho = services.create_recipe(
            organization=restaurant.organization, name="Molho de natas", kind=Recipe.Kind.PREPARACAO, user=manager,
            portions=Decimal(10), lines=[(("Natas", "L"), Decimal(1), None)],
        )
        ficha = _bitoque(restaurant, manager, lines=BITOQUE + [(molho, Decimal("0.5"), None)])
        custo = services.recipe_cost(ficha.current_version(), restaurant)
        assert custo.lines[-1].cost == Decimal("0.2000")
        assert custo.per_dose == Decimal("2.87")

    def test_food_cost_usa_o_preco_de_referencia_sem_pos(self, restaurant, manager, artigos):
        ficha = _bitoque(restaurant, manager, sale_price=Decimal("9.00"))
        [linha] = services.summaries([ficha], restaurant)
        assert (linha["price"], linha["product"], linha["food_cost"]) == (Decimal("9.00"), None, Decimal("29.7"))
        produto = _produto(restaurant)
        services.link_product(recipe=ficha, product=produto, user=manager)
        [linha] = services.summaries([ficha], restaurant)
        assert (linha["price"], linha["product"]) == (Decimal("8.94"), produto)


class TestVersoes:
    def test_recipe_version_used_for_past_day(self, restaurant, manager, artigos):
        """O consumo de um dia passado usa a versão da ficha desse dia."""
        ficha = _bitoque(restaurant, manager, valid_from=HOJE() - datetime.timedelta(days=30))
        maior = [(("Bife da vazia", "KG"), Decimal("0.200"), None)] + BITOQUE[1:]
        nova = services.save_version(recipe=ficha, portions=1, notes="", lines=maior, user=manager, valid_from=HOJE() - datetime.timedelta(days=5))
        assert nova.number == 2
        antes = ficha.version_on(HOJE() - datetime.timedelta(days=10))
        assert antes.number == 1
        assert antes.lines.get(item_name="Bife da vazia").quantity == Decimal("0.180")
        assert ficha.version_on(HOJE()) == nova == ficha.current_version()
        assert ficha.version_on(HOJE() - datetime.timedelta(days=31)) is None
        # O custo de um dia passado usa a versão desse dia.
        custo = services.recipe_cost(antes, restaurant, day=HOJE() - datetime.timedelta(days=10))
        assert custo.per_dose == Decimal("2.67")

    def test_sem_mudancas_nao_cria_versao(self, restaurant, manager, artigos):
        ficha = _bitoque(restaurant, manager)
        assert services.save_version(recipe=ficha, portions=Decimal("1.0"), notes="", lines=BITOQUE, user=manager) is None
        assert ficha.versions.count() == 1

    def test_versao_nova_nao_pode_comecar_antes_da_ultima(self, restaurant, manager, artigos):
        ficha = _bitoque(restaurant, manager)
        with pytest.raises(ValidationError, match="a partir de"):
            services.save_version(
                recipe=ficha, portions=2, notes="", lines=BITOQUE, user=manager, valid_from=HOJE() - datetime.timedelta(days=1)
            )

    def test_versao_futura_nao_vale_hoje(self, restaurant, manager, artigos):
        ficha = _bitoque(restaurant, manager)
        services.save_version(recipe=ficha, portions=2, notes="", lines=BITOQUE, user=manager, valid_from=HOJE() + datetime.timedelta(days=7))
        assert ficha.current_version().number == 1

    def test_editar_pelo_ecra_cria_versao(self, client, restaurant, stock_user, artigos):
        ficha = _bitoque(restaurant, stock_user)
        client.force_login(stock_user)
        r = client.get(reverse("recipes:editar", args=[ficha.pk]))
        assert r.status_code == 200
        dados = {"nome": "Bitoque da casa", "tipo": "PRATO", "preco": "9", "doses": "1", "notas": "", "desde": HOJE().isoformat()}
        linhas = r.context["linhas"]
        dados["n_linhas"] = len(linhas)
        for i, l in enumerate(linhas):
            dados.update({f"ing-{i}": l["ing"], f"qtd-{i}": l["qtd"], f"quebra-{i}": l["quebra"]})
        dados["qtd-1"] = "2"  # dois ovos
        client.post(reverse("recipes:editar", args=[ficha.pk]), dados)
        ficha.refresh_from_db()
        assert (ficha.name, ficha.sale_price) == ("Bitoque da casa", Decimal(9))
        assert ficha.versions.count() == 2
        assert ficha.current_version().lines.get(item_name="Ovo").quantity == 2
        assert RecipeVersion.objects.get(recipe=ficha, number=1).lines.get(item_name="Ovo").quantity == 1


class TestRegras:
    def test_preparacao_so_um_nivel(self, restaurant, manager, artigos):
        base = services.create_recipe(
            organization=restaurant.organization, name="Refogado", kind=Recipe.Kind.PREPARACAO, user=manager,
            lines=[(("Batata", "KG"), Decimal("0.1"), None)],
        )
        with pytest.raises(ValidationError, match="não leva outras preparações"):
            services.create_recipe(
                organization=restaurant.organization, name="Molho", kind=Recipe.Kind.PREPARACAO, user=manager,
                lines=[(base, Decimal(1), None)],
            )
        assert not Recipe.objects.filter(name="Molho").exists()

    def test_so_preparacoes_entram_noutras_fichas(self, restaurant, manager, artigos):
        prato = _bitoque(restaurant, manager)
        with pytest.raises(ValidationError, match="não é uma preparação"):
            services.create_recipe(
                organization=restaurant.organization, name="Menu", kind=Recipe.Kind.PRATO, user=manager,
                lines=[(prato, Decimal(1), None)],
            )

    def test_preparacao_usada_continua_preparacao(self, restaurant, manager, artigos):
        molho = services.create_recipe(
            organization=restaurant.organization, name="Molho", kind=Recipe.Kind.PREPARACAO, user=manager,
            lines=[(("Batata", "KG"), Decimal("0.1"), None)],
        )
        ficha = _bitoque(restaurant, manager, lines=BITOQUE + [(molho, Decimal(1), None)])
        with pytest.raises(ValidationError, match="continua a ser uma preparação"):
            services.save_recipe(organization=restaurant.organization, name="Molho", kind=Recipe.Kind.PRATO, recipe=molho)
        with pytest.raises(ValidationError, match="Bitoque"):
            services.set_active(recipe=molho, active=False)
        services.set_active(recipe=ficha, active=False)
        services.set_active(recipe=molho, active=False)

    def test_artigo_repetido_e_quebra_invalida(self, restaurant, manager, artigos):
        with pytest.raises(ValidationError, match="duas vezes"):
            _bitoque(restaurant, manager, lines=BITOQUE + [(("ovo", "UN"), Decimal(1), None)])
        with pytest.raises(ValidationError, match="quebra"):
            _bitoque(restaurant, manager, lines=[(("Batata", "KG"), Decimal("0.2"), Decimal(100))])

    def test_nome_unico_no_grupo(self, restaurant, manager, artigos):
        _bitoque(restaurant, manager)
        with pytest.raises(ValidationError, match="Já há uma ficha"):
            services.create_recipe(organization=restaurant.organization, name="bitoque", kind=Recipe.Kind.PRATO, user=manager)

    def test_artigo_renomeado_continua_ligado(self, restaurant, manager, artigos):
        ficha = _bitoque(restaurant, manager)
        artigos["ovo"].name = "Ovo M"
        artigos["ovo"].save()
        assert ficha.current_version().lines.filter(item_name="Ovo M").exists()
        assert services.recipe_cost(ficha.current_version(), restaurant).complete


class TestPos:
    def test_um_produto_tem_uma_so_ficha(self, restaurant, manager, artigos):
        produto = _produto(restaurant)
        ficha = _bitoque(restaurant, manager)
        outra = services.create_recipe(organization=restaurant.organization, name="Prato do dia", kind=Recipe.Kind.PRATO, user=manager)
        services.link_product(recipe=ficha, product=produto, user=manager)
        services.link_product(recipe=ficha, product=produto, user=manager)  # repetir não muda nada
        with pytest.raises(ValidationError, match="já está ligado"):
            services.link_product(recipe=outra, product=produto, user=manager)

    def test_produtos_de_varias_casas_na_mesma_ficha(self, restaurant, manager, artigos):
        ribeira = Restaurant.objects.create(name="Ribeira", slug="ribeira", organization=restaurant.organization)
        ficha = _bitoque(restaurant, manager)
        services.link_product(recipe=ficha, product=_produto(restaurant), user=manager)
        services.link_product(recipe=ficha, product=_produto(ribeira, code="PR-BIT", preco="9.29"), user=manager)
        assert ficha.products.count() == 2
        assert services.sale_price(ficha, ribeira)[0] == Decimal("9.29")

    def test_produto_de_outro_grupo_recusado(self, restaurant, manager, artigos):
        fora = Restaurant.objects.create(name="Outro grupo", slug="outro")
        with pytest.raises(ValidationError, match="outro grupo"):
            services.link_product(recipe=_bitoque(restaurant, manager), product=_produto(fora), user=manager)

    def test_produtos_sem_ficha_pelo_peso_nas_vendas(self, client, restaurant, manager, artigos):
        restaurant.nif = "509123457"
        restaurant.save()
        ontem = HOJE() - datetime.timedelta(days=1)
        hora = datetime.datetime.combine(ontem, datetime.time(13))
        docs = [
            Doc("FS E/1", hora, [("P001", "Bitoque", 1, Decimal("8.94"), Decimal("13")), ("B001", "Imperial", 2, Decimal("1.46"), Decimal("23"))]),
            Doc("FS E/2", hora, [("P003", "Bacalhau à Brás", 2, Decimal("10.62"), Decimal("13"))]),
        ]
        conteudo = sintetico.gerar(nif=restaurant.nif, documentos=docs, inicio=ontem, fim=ontem)
        import_saft(restaurant=restaurant, upload=SimpleUploadedFile("saft.xml", conteudo), user=manager)
        services.link_product(recipe=_bitoque(restaurant, manager), product=PosProduct.objects.get(code="P001"), user=manager)

        linhas, parte = services.products_without_recipe(restaurant)
        assert [l["product"].code for l in linhas][:2] == ["P003", "B001"]
        assert linhas[0]["value"] == Decimal("21.24") and linhas[0]["share"] == Decimal("64.2")
        assert parte == Decimal("73.0")  # (21,24 + 2,92) / 33,10

        client.force_login(manager)
        r = client.get(reverse("recipes:pos"))
        assert "Bacalhau à Brás" in r.content.decode() and "21,24" in r.content.decode()

    def test_resp_stock_nao_ve_valores_de_vendas(self, client, restaurant, stock_user):
        _produto(restaurant)
        client.force_login(stock_user)
        r = client.get(reverse("recipes:pos"))
        assert r.status_code == 200 and "Vendas sem IVA" not in r.content.decode()

    def test_criar_ficha_a_partir_do_produto_liga_o(self, client, restaurant, manager, artigos):
        produto = _produto(restaurant, code="P003", descricao="Bacalhau à Brás", preco="10.62")
        client.force_login(manager)
        r = client.get(reverse("recipes:nova") + f"?produto={produto.pk}")
        assert r.context["dados"]["nome"] == "Bacalhau à Brás"
        dados = dict(r.context["dados"], n_linhas=1, **{"ing-0": "a:KG:Batata", "qtd-0": "0,15", "quebra-0": "20"})
        client.post(reverse("recipes:nova"), dados)
        assert RecipeProduct.objects.get(product=produto).recipe.name == "Bacalhau à Brás"


class TestAcesso:
    def test_colaborador_nao_entra(self, client, staff_user):
        client.force_login(staff_user)
        assert client.get(reverse("recipes:lista")).status_code == 403

    def test_fichas_de_outro_grupo_invisiveis(self, client, restaurant, manager, artigos):
        fora = Restaurant.objects.create(name="Outro grupo", slug="outro")
        alheia = services.create_recipe(organization=fora.organization, name="Segredo", kind=Recipe.Kind.PRATO, user=manager)
        client.force_login(manager)
        assert client.get(reverse("recipes:ficha", args=[alheia.pk])).status_code == 404
        assert "Segredo" not in client.get(reverse("recipes:lista")).content.decode()

    def test_paginas_abrem(self, client, restaurant, stock_user, artigos):
        ficha = _bitoque(restaurant, stock_user)
        client.force_login(stock_user)
        for url in (
            reverse("recipes:lista"),
            reverse("recipes:nova"),
            reverse("recipes:ficha", args=[ficha.pk]),
            reverse("recipes:imprimir", args=[ficha.pk]) + "?doses=10",
        ):
            assert client.get(url).status_code == 200, url

    def test_ficha_para_dez_doses(self, client, restaurant, stock_user, artigos):
        ficha = _bitoque(restaurant, stock_user)
        client.force_login(stock_user)
        r = client.get(reverse("recipes:imprimir", args=[ficha.pk]) + "?doses=10")
        batata = next(l for l in r.context["linhas"] if l["line"].item_name == "Batata")
        assert (batata["net"], batata["gross"]) == (Decimal("2.000"), Decimal("2.500"))
        assert "€" not in r.content.decode()
