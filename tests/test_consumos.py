"""Fase 12: consumos internos. Saem do stock pelo register_movement(), valem o
custo do momento, não se apagam e cada um vê só os seus."""
import datetime
from decimal import Decimal

import pytest
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from attendance.models import TimeEntry
from core.models import Restaurant
from inventory import consumption as servico
from inventory.models import Category, ConsumptionSettings, InternalConsumption, Item, StockMovement
from inventory.services import register_movement
from workers.models import Worker

pytestmark = pytest.mark.django_db
REFEICAO = InternalConsumption.Reason.REFEICAO


def _artigo(restaurant, nome, stock, custo, user, unidade=Item.Unit.UN):
    categoria = Category.objects.get_or_create(restaurant=restaurant, name="Bebidas")[0]
    item = Item.objects.create(
        restaurant=restaurant, name=nome, category=categoria, unit=unidade,
        reference_cost=None if custo is None else Decimal(custo),
    )
    register_movement(item=item, movement_type=StockMovement.Type.ENTRADA, quantity=Decimal(stock), user=user)
    item.refresh_from_db()
    return item


@pytest.fixture
def cafe(restaurant, manager):
    return _artigo(restaurant, "Café", 100, "0.18", manager)


@pytest.fixture
def agua(restaurant, manager):
    return _artigo(restaurant, "Água 0,5 l", 48, "0.25", manager)


@pytest.fixture
def marta(restaurant, staff_user):
    return Worker.objects.create(restaurant=restaurant, full_name="Marta Silva", user=staff_user)


@pytest.fixture
def rui(restaurant, stock_user):
    return Worker.objects.create(restaurant=restaurant, full_name="Rui Gomes", user=stock_user)


def _consumo(restaurant, worker, linhas, user, reason=REFEICAO, day=None):
    return servico.register_consumption(
        restaurant=restaurant, worker=worker, reason=reason, day=day or timezone.localdate(), lines=linhas, user=user
    )


class TestRegisto:
    def test_aceitacao_cafe_e_agua_de_dois_trabalhadores(self, client, restaurant, manager, cafe, agua, marta, rui, staff_user):
        """Critério de aceitação da Fase 12."""
        client.force_login(manager)
        hoje = timezone.localdate().isoformat()
        for w in (marta, rui):
            resp = client.post(reverse("inventory:consumo_novo"), {
                "pessoa": w.pk, "motivo": REFEICAO, "dia": hoje,
                "item-0": cafe.pk, "qtd-0": "1", "item-1": agua.pk, "qtd-1": "1",
            })
            assert resp.status_code == 302
        # O stock desce.
        assert Item.objects.get(pk=cafe.pk).current_stock == 98
        assert Item.objects.get(pk=agua.pk).current_stock == 46
        # Cada um vê o seu na app, e não o do outro.
        client.force_login(staff_user)
        html = client.get(reverse("staff:consumos")).content.decode()
        assert "0,43 €" in html and "Café" in html
        assert html.count("data-consumo") == 1
        # O mapa do mês tem o valor por pessoa.
        mapa = servico.month_map(restaurant, timezone.localdate().replace(day=1))
        assert [(p["quem"], p["refeicoes"], p["valor"]) for p in mapa] == [
            ("Marta Silva", 1, Decimal("0.43")), ("Rui Gomes", 1, Decimal("0.43"))
        ]

    def test_saida_de_origem_consumo_com_o_custo_do_momento(self, restaurant, manager, cafe, marta):
        consumo = _consumo(restaurant, marta, [(cafe, Decimal(2))], manager)
        linha = consumo.lines.get()
        mov = linha.movement
        assert (mov.movement_type, mov.origin, mov.reference) == (StockMovement.Type.SAIDA, StockMovement.Origin.CONSUMO, consumo.reference)
        assert "Marta Silva" in mov.reason and mov.created_by == manager
        assert (linha.unit_cost, linha.value) == (Decimal("0.18"), Decimal("0.36"))
        # O custo muda depois; o valor do consumo não.
        Item.objects.filter(pk=cafe.pk).update(reference_cost=Decimal("0.30"))
        linha.refresh_from_db()
        assert linha.value == Decimal("0.36")

    def test_consumo_da_casa_e_artigo_sem_custo(self, restaurant, manager, cafe):
        vinho = _artigo(restaurant, "Vinho da casa", 10, None, manager)
        consumo = _consumo(restaurant, None, [(vinho, Decimal(1)), (cafe, Decimal(1))], manager, reason=InternalConsumption.Reason.OFERTA)
        assert consumo.who == "A casa"
        assert consumo.value() is None
        mapa = servico.month_map(restaurant, timezone.localdate().replace(day=1))
        assert (mapa[0]["quem"], mapa[0]["outros"], mapa[0]["valor"], mapa[0]["sem_custo"]) == ("A casa", 1, Decimal("0.18"), 1)

    def test_validacoes(self, restaurant, manager, cafe, marta):
        with pytest.raises(ValidationError, match="de um trabalhador"):
            _consumo(restaurant, None, [(cafe, Decimal(1))], manager)
        with pytest.raises(ValidationError, match="futuro"):
            _consumo(restaurant, marta, [(cafe, Decimal(1))], manager, day=timezone.localdate() + datetime.timedelta(days=1))
        with pytest.raises(ValidationError, match="pelo menos um artigo"):
            _consumo(restaurant, marta, [(cafe, None)], manager)
        outra = Restaurant.objects.create(organization=restaurant.organization, name="Baixa", slug="baixa")
        de_fora = _artigo(outra, "Café da Baixa", 5, "0.2", manager)
        with pytest.raises(ValidationError, match="não é um artigo desta casa"):
            _consumo(restaurant, marta, [(de_fora, Decimal(1))], manager)
        assert not InternalConsumption.objects.exists()
        assert Item.objects.get(pk=cafe.pk).current_stock == 100


class TestLimite:
    def test_passar_o_limite_avisa_mas_nao_bloqueia(self, client, restaurant, manager, cafe, marta):
        regras = ConsumptionSettings.for_restaurant(restaurant)
        regras.meals_per_shift = 1
        regras.save()
        # Uma entrada no início do dia de hoje, para o teste não depender da hora.
        inicio = timezone.make_aware(datetime.datetime.combine(timezone.localdate(), datetime.time(0, 1)))
        TimeEntry.objects.create(worker=marta, check_in=inicio)
        primeiro = _consumo(restaurant, marta, [(cafe, Decimal(1))], manager)
        assert not primeiro.over_limit
        client.force_login(manager)
        resp = client.post(reverse("inventory:consumo_novo"), {
            "pessoa": marta.pk, "motivo": REFEICAO, "dia": timezone.localdate().isoformat(), "item-0": cafe.pk, "qtd-0": "1",
        }, follow=True)
        segundo = InternalConsumption.objects.latest("pk")
        assert segundo.over_limit
        assert "passou o limite" in resp.content.decode()
        # Uma oferta não conta para o limite das refeições.
        assert not _consumo(restaurant, marta, [(cafe, Decimal(1))], manager, reason=InternalConsumption.Reason.OFERTA).over_limit

    def test_sem_limite_nunca_avisa(self, restaurant, manager, cafe, marta):
        for _ in range(3):
            assert not _consumo(restaurant, marta, [(cafe, Decimal(1))], manager).over_limit


class TestAnulacao:
    def test_anular_repoe_o_stock_e_sai_do_mapa(self, client, restaurant, manager, cafe, marta):
        consumo = _consumo(restaurant, marta, [(cafe, Decimal(3))], manager)
        client.force_login(manager)
        client.post(reverse("inventory:consumo_anular", args=[consumo.pk]), {"motivo": "era do Rui"})
        consumo.refresh_from_db()
        assert consumo.cancelled_by == manager and consumo.cancel_reason == "era do Rui"
        assert Item.objects.get(pk=cafe.pk).current_stock == 100
        reversao = consumo.lines.get().reversal
        assert (reversao.movement_type, reversao.origin) == (StockMovement.Type.ENTRADA, StockMovement.Origin.CONSUMO)
        assert servico.month_map(restaurant, timezone.localdate().replace(day=1)) == []
        with pytest.raises(ValidationError, match="já estava anulado"):
            servico.cancel_consumption(consumption=consumo, user=manager, reason="outra vez")

    def test_anular_pede_motivo(self, restaurant, manager, cafe, marta):
        consumo = _consumo(restaurant, marta, [(cafe, Decimal(1))], manager)
        with pytest.raises(ValidationError, match="motivo"):
            servico.cancel_consumption(consumption=consumo, user=manager, reason=" ")

    def test_consumo_nao_se_apaga_no_admin(self, rf, admin_user):
        pedido = rf.get("/")
        pedido.user = admin_user
        modelo = admin.site._registry[InternalConsumption]
        assert not modelo.has_delete_permission(pedido) and not modelo.has_change_permission(pedido)


class TestAcessos:
    def test_staff_sees_only_own_consumption(self, client, restaurant, manager, cafe, marta, rui, staff_user):
        _consumo(restaurant, marta, [(cafe, Decimal(1))], manager)
        _consumo(restaurant, rui, [(cafe, Decimal(5))], manager)
        client.force_login(staff_user)
        html = client.get(reverse("staff:consumos")).content.decode()
        assert "Café 1 un" in html and "Café 5 un" not in html
        # O backoffice dos consumos está fechado ao colaborador.
        assert client.get(reverse("inventory:consumos")).status_code == 403
        assert client.post(reverse("inventory:consumo_novo"), {}).status_code == 403

    def test_resp_stock_ve_mas_nao_regista_dos_outros_e_so_o_admin_mexe_nas_regras(
        self, client, restaurant, stock_user, manager, admin_user, cafe, marta
    ):
        consumo = _consumo(restaurant, marta, [(cafe, Decimal(1))], manager)
        client.force_login(stock_user)
        html = client.get(reverse("inventory:consumos")).content.decode()
        assert "Café 1 un" in html and reverse("inventory:consumo_novo") not in html and "Alterar" not in html
        assert client.get(reverse("inventory:consumo_novo")).status_code == 403
        assert client.post(reverse("inventory:consumo_novo"), {}).status_code == 403
        assert client.get(reverse("inventory:consumo_alterar", args=[consumo.pk])).status_code == 403
        assert client.post(reverse("inventory:consumo_anular", args=[consumo.pk]), {"motivo": "x"}).status_code == 403
        assert client.get(reverse("inventory:consumo_regras")).status_code == 403
        client.force_login(manager)
        assert client.get(reverse("inventory:consumo_regras")).status_code == 403
        client.force_login(admin_user)
        client.post(reverse("inventory:consumo_regras"), {"meals_per_shift": "1"})
        assert ConsumptionSettings.objects.get(restaurant=restaurant).meals_per_shift == 1

    def test_consumo_de_outra_casa_nao_se_anula(self, client, restaurant, manager, marta, cafe):
        outra = Restaurant.objects.create(organization=restaurant.organization, name="Baixa", slug="baixa")
        w = Worker.objects.create(restaurant=outra, full_name="Ana")
        item = _artigo(outra, "Café B", 5, "0.2", manager)
        consumo = _consumo(outra, w, [(item, Decimal(1))], manager)
        client.force_login(manager)
        assert client.post(reverse("inventory:consumo_anular", args=[consumo.pk]), {"motivo": "x"}).status_code == 404

    def test_ecras_e_exportacao(self, client, restaurant, manager, cafe, agua, marta):
        _consumo(restaurant, marta, [(cafe, Decimal(1)), (agua, Decimal(2))], manager)
        client.force_login(manager)
        mes = timezone.localdate().strftime("%Y-%m")
        assert client.get(reverse("inventory:consumos")).status_code == 200
        assert client.get(reverse("inventory:consumos"), {"pessoa": marta.pk}).status_code == 200
        assert client.get(reverse("inventory:consumos"), {"pessoa": "casa"}).status_code == 200
        texto = client.get(reverse("inventory:consumos"), {"mes": mes, "exportar": "1"}).content.decode("utf-8-sig")
        assert f"Marta Silva;{timezone.localdate().isoformat()};Refeição do pessoal;Água 0,5 l;2;UN;0,25;0,5;;CI-" in texto
        assert "Marta Silva;1;0;0,68;" in texto
        resp = client.post(reverse("inventory:consumo_novo"), {"pessoa": "", "motivo": REFEICAO})
        assert resp.status_code == 400 and "Escolha quem consumiu" in resp.content.decode()


class TestStockNegativo:
    def test_consumo_sem_stock_regista_e_fica_negativo(self, restaurant, manager, cafe, marta):
        consumo = _consumo(restaurant, marta, [(cafe, Decimal(101))], manager)
        cafe.refresh_from_db()
        assert cafe.current_stock == -1 and cafe.needs_count
        assert consumo.negativos == [(cafe, Decimal(-1))]

    def test_vista_avisa_do_stock_negativo(self, client, restaurant, manager, cafe, marta):
        client.force_login(manager)
        resp = client.post(reverse("inventory:consumo_novo"), {
            "pessoa": marta.pk, "motivo": REFEICAO, "dia": timezone.localdate().isoformat(),
            "item-0": cafe.pk, "qtd-0": "102",
        }, follow=True)
        html = resp.content.decode()
        assert "Stock negativo: Café em -2 un" in html
        assert Item.objects.get(pk=cafe.pk).current_stock == -2

    def test_outros_movimentos_continuam_a_recusar(self, manager, cafe):
        with pytest.raises(ValidationError, match="deixaria o stock"):
            register_movement(item=cafe, movement_type=StockMovement.Type.SAIDA, quantity=Decimal(101), user=manager)


class TestLinhas:
    def test_formulario_mostra_tres_linhas_e_aceita_mais(self, client, restaurant, manager, cafe, agua, marta):
        client.force_login(manager)
        html = client.get(reverse("inventory:consumo_novo")).content.decode()
        assert "visiveis: 3," in html and 'aria-label="Acrescentar uma linha"' in html
        # Uma linha aberta com o + (índice 7) também conta.
        resp = client.post(reverse("inventory:consumo_novo"), {
            "pessoa": marta.pk, "motivo": REFEICAO, "dia": timezone.localdate().isoformat(),
            "item-0": cafe.pk, "qtd-0": "1", "item-7": agua.pk, "qtd-7": "2",
        })
        assert resp.status_code == 302
        assert InternalConsumption.objects.get().lines.count() == 2

    def test_erro_mantem_as_linhas_abertas(self, client, restaurant, manager, cafe, marta):
        client.force_login(manager)
        resp = client.post(reverse("inventory:consumo_novo"), {
            "pessoa": "", "motivo": REFEICAO, "item-4": cafe.pk, "qtd-4": "1",
        })
        assert resp.status_code == 400 and "visiveis: 5," in resp.content.decode()


class TestAlterar:
    def test_gerente_altera_consumo_de_outro(self, client, restaurant, manager, cafe, agua, marta):
        antigo = _consumo(restaurant, marta, [(cafe, Decimal(2))], manager)
        client.force_login(manager)
        html = client.get(reverse("inventory:consumo_alterar", args=[antigo.pk])).content.decode()
        assert f"Alterar consumo {antigo.reference}" in html
        resp = client.post(reverse("inventory:consumo_alterar", args=[antigo.pk]), {
            "pessoa": marta.pk, "motivo": REFEICAO, "dia": timezone.localdate().isoformat(),
            "item-0": cafe.pk, "qtd-0": "1", "item-1": agua.pk, "qtd-1": "1",
        })
        assert resp.status_code == 302
        antigo.refresh_from_db()
        assert antigo.cancelled_at is not None and antigo.cancel_reason.startswith("Alterado: substituído por CI-")
        assert Item.objects.get(pk=cafe.pk).current_stock == 99
        assert Item.objects.get(pk=agua.pk).current_stock == 47
        assert InternalConsumption.objects.filter(cancelled_at__isnull=True).count() == 1

    def test_alterar_com_erro_nao_muda_nada(self, client, restaurant, manager, cafe, marta):
        antigo = _consumo(restaurant, marta, [(cafe, Decimal(2))], manager)
        client.force_login(manager)
        resp = client.post(reverse("inventory:consumo_alterar", args=[antigo.pk]), {
            "pessoa": marta.pk, "motivo": REFEICAO, "dia": timezone.localdate().isoformat(),
        })
        assert resp.status_code == 400
        antigo.refresh_from_db()
        assert antigo.cancelled_at is None and Item.objects.get(pk=cafe.pk).current_stock == 98


class TestColaborador:
    def test_regista_o_seu_consumo_na_app(self, client, restaurant, staff_user, cafe, marta):
        client.force_login(staff_user)
        html = client.get(reverse("staff:consumo_novo")).content.decode()
        assert "visiveis: 3," in html and 'value="DONO"' not in html
        resp = client.post(reverse("staff:consumo_novo"), {
            "motivo": REFEICAO, "dia": timezone.localdate().isoformat(), "item-0": cafe.pk, "qtd-0": "1",
            # Tentar registar em nome de outra pessoa não tem efeito: a pessoa é sempre o próprio.
            "pessoa": "casa",
        })
        assert resp.status_code == 302
        consumo = InternalConsumption.objects.get()
        assert consumo.worker == marta and consumo.created_by == staff_user and consumo.restaurant == restaurant

    def test_altera_e_anula_o_seu(self, client, restaurant, staff_user, manager, cafe, marta):
        consumo = _consumo(restaurant, marta, [(cafe, Decimal(1))], manager)
        client.force_login(staff_user)
        resp = client.post(reverse("staff:consumo_alterar", args=[consumo.pk]), {
            "motivo": REFEICAO, "dia": timezone.localdate().isoformat(), "item-0": cafe.pk, "qtd-0": "3",
        })
        assert resp.status_code == 302
        novo = InternalConsumption.objects.get(cancelled_at__isnull=True)
        assert novo.worker == marta and Item.objects.get(pk=cafe.pk).current_stock == 97
        resp = client.post(reverse("staff:consumo_anular", args=[novo.pk]), {})
        assert resp.status_code == 302
        assert not InternalConsumption.objects.filter(cancelled_at__isnull=True).exists()
        assert Item.objects.get(pk=cafe.pk).current_stock == 100

    def test_nao_mexe_nos_consumos_dos_outros(self, client, restaurant, staff_user, manager, cafe, marta, rui):
        do_rui = _consumo(restaurant, rui, [(cafe, Decimal(1))], manager)
        client.force_login(staff_user)
        assert client.get(reverse("staff:consumo_alterar", args=[do_rui.pk])).status_code == 404
        assert client.post(reverse("staff:consumo_alterar", args=[do_rui.pk]), {
            "motivo": REFEICAO, "dia": timezone.localdate().isoformat(), "item-0": cafe.pk, "qtd-0": "9",
        }).status_code == 404
        assert client.post(reverse("staff:consumo_anular", args=[do_rui.pk]), {}).status_code == 404
        do_rui.refresh_from_db()
        assert do_rui.cancelled_at is None

    def test_colaborador_sem_stock_regista_com_aviso(self, client, restaurant, staff_user, cafe, marta):
        client.force_login(staff_user)
        resp = client.post(reverse("staff:consumo_novo"), {
            "motivo": REFEICAO, "dia": timezone.localdate().isoformat(), "item-0": cafe.pk, "qtd-0": "105",
        }, follow=True)
        assert "Stock negativo: Café em -5 un" in resp.content.decode()
