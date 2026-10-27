"""Fase 9: um trabalhador em mais de uma casa do grupo. A casa principal
tem a ficha, as férias e o fecho do mês; nas outras, a pessoa pica e tem
turnos. Cada registo fica na casa onde foi picado, e cada casa só vê o que
lá aconteceu."""
import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from attendance import month as mes
from attendance.models import TimeEntry
from attendance.services import close_shift, decide_correction, open_shift, request_correction
from core.middleware import SESSION_KEY
from core.models import Restaurant
from inventory.consumption import register_consumption
from inventory.models import Category, Item, InternalConsumption, StockMovement
from inventory.services import register_movement
from shifts import services as turnos
from shifts.models import Shift
from tests.quiosque import ativar_tablet, escrever_codigo, picar
from workers.models import Worker

pytestmark = pytest.mark.django_db
User = get_user_model()
T = datetime.time


@pytest.fixture
def casa_b(restaurant):
    return Restaurant.objects.create(organization=restaurant.organization, name="Tasca da Baixa", slug="tasca-da-baixa")


@pytest.fixture
def gerente_b(casa_b):
    return User.objects.create_user(
        email="gerente.b@tasca.pt", password="segredo-de-teste-123", restaurant=casa_b, role=User.Role.MANAGER
    )


@pytest.fixture
def marta(restaurant, casa_b):
    """Da casa principal (a do teste), também trabalha na Baixa."""
    w = Worker.objects.create(restaurant=restaurant, full_name="Marta Silva")
    w.other_restaurants.add(casa_b)
    w.set_kiosk_code("2468")
    return w


def _na_casa(client, user, casa):
    client.force_login(user)
    sessao = client.session
    sessao[SESSION_KEY] = casa.pk
    sessao.save()


def _quando(dia, hora):
    return timezone.make_aware(datetime.datetime.combine(dia, T(hora)))


class TestModelo:
    def test_in_restaurant_includes_visitors(self, restaurant, casa_b, marta):
        so_b = Worker.objects.create(restaurant=casa_b, full_name="Ana da Baixa")
        assert set(Worker.objects.in_restaurant(casa_b)) == {marta, so_b}
        assert list(Worker.objects.in_restaurant(restaurant)) == [marta]
        assert marta.works_in(casa_b) and not so_b.works_in(restaurant)
        assert marta.restaurants() == [restaurant, casa_b]

    def test_entry_stays_in_the_house_where_it_was_punched(self, restaurant, casa_b, marta):
        entrada = open_shift(worker=marta, restaurant=casa_b)
        assert entrada.restaurant == casa_b
        close_shift(worker=marta)
        assert open_shift(worker=marta).restaurant == restaurant

    def test_cannot_punch_in_a_house_where_one_does_not_work(self, restaurant, casa_b):
        so_a = Worker.objects.create(restaurant=restaurant, full_name="Rui Costa")
        with pytest.raises(ValidationError, match="não trabalha"):
            open_shift(worker=so_a, restaurant=casa_b)

    def test_open_entry_elsewhere_becomes_unresolved(self, restaurant, casa_b, marta):
        """Uma entrada aberta noutra casa conta como saída esquecida: a
        pessoa já está aqui."""
        agora = timezone.now()
        em_a = open_shift(worker=marta, at=agora - datetime.timedelta(hours=3))
        em_b = open_shift(worker=marta, at=agora, restaurant=casa_b)
        em_a.refresh_from_db()
        assert em_a.missing_exit and em_a.is_unresolved()
        assert marta.open_entry == em_b


class TestQuiosque:
    def test_tablet_of_other_house_shows_visitor_and_records_there(self, client, restaurant, casa_b, gerente_b, marta):
        ativar_tablet(client, gerente_b)
        assert "Marta Silva" in client.get(reverse("kiosk:inicio")).content.decode()
        picar(client, marta, "entrada")
        entrada = TimeEntry.objects.get(worker=marta)
        assert entrada.restaurant == casa_b

    def test_open_entry_in_other_house_is_not_closed_here(self, client, restaurant, casa_b, gerente_b, marta):
        open_shift(worker=marta, at=timezone.now() - datetime.timedelta(hours=2))
        ativar_tablet(client, gerente_b)
        resp = escrever_codigo(client, marta)
        corpo = resp.content.decode()
        assert "Tem a entrada aberta em Tasca do Teste" in corpo
        assert resp.context["entry"] is None
        resp = picar(client, marta, "saida")
        assert "outra casa" in resp.content.decode()
        assert TimeEntry.objects.get(worker=marta).check_out is None


class TestPontoNoBackoffice:
    def test_each_house_sees_only_its_entries(self, client, restaurant, casa_b, manager, gerente_b, marta):
        hoje = timezone.localdate()
        open_shift(worker=marta, at=_quando(hoje, 0), restaurant=casa_b)
        _na_casa(client, gerente_b, casa_b)
        corpo = client.get(reverse("attendance:dia")).content.decode()
        assert "Marta Silva" in corpo and "de Tasca do Teste" in corpo
        _na_casa(client, manager, restaurant)
        resp = client.get(reverse("attendance:dia"))
        linha = next(l for l in resp.context["linhas"] if l["worker"] == marta)
        assert linha["registos"] == []

    def test_visitor_without_activity_is_not_listed(self, client, casa_b, gerente_b, marta):
        _na_casa(client, gerente_b, casa_b)
        assert "Marta Silva" not in client.get(reverse("attendance:dia")).content.decode()

    def test_correction_goes_to_the_house_of_the_entry(self, client, restaurant, casa_b, manager, gerente_b, marta):
        inicio = timezone.now() - datetime.timedelta(hours=5)
        entrada = open_shift(worker=marta, at=inicio, restaurant=casa_b)
        pedido = request_correction(
            worker=marta, entry=entrada, note="esqueci a saída", check_in=inicio, check_out=inicio + datetime.timedelta(hours=4)
        )
        assert pedido.restaurant == casa_b
        _na_casa(client, manager, restaurant)
        assert client.post(reverse("attendance:decidir_pedido", args=[pedido.pk, "aprovar"])).status_code == 404
        _na_casa(client, gerente_b, casa_b)
        client.post(reverse("attendance:decidir_pedido", args=[pedido.pk, "aprovar"]))
        entrada.refresh_from_db()
        assert entrada.check_out is not None

    def test_missing_entry_request_is_created_in_the_chosen_house(self, client, restaurant, casa_b, gerente_b, marta):
        ontem = timezone.localdate() - datetime.timedelta(days=1)
        pedido = request_correction(
            worker=marta, note="o tablet estava desligado", check_in=_quando(ontem, 12),
            check_out=_quando(ontem, 16), restaurant=casa_b,
        )
        assert pedido.restaurant == casa_b
        decide_correction(request_obj=pedido, user=gerente_b, approve=True)
        assert TimeEntry.objects.get(worker=marta).restaurant == casa_b

    def test_staff_app_asks_which_house(self, client, restaurant, casa_b, marta):
        conta = User.objects.create_user(
            email="marta@tasca.pt", password="segredo-de-teste-123", restaurant=restaurant, role=User.Role.STAFF
        )
        marta.user = conta
        marta.save()
        client.force_login(conta)
        resp = client.get(reverse("staff:correcao_nova"))
        assert "restaurant" in resp.context["form"].fields
        ontem = timezone.localdate() - datetime.timedelta(days=1)
        client.post(
            reverse("staff:correcao_nova"),
            {"restaurant": casa_b.pk, "check_in": f"{ontem}T12:00", "check_out": f"{ontem}T16:00", "note": "sem tablet"},
        )
        assert marta.correction_requests.get().restaurant == casa_b

    def test_manager_adds_entry_in_the_active_house(self, client, casa_b, gerente_b, marta):
        _na_casa(client, gerente_b, casa_b)
        ontem = timezone.localdate() - datetime.timedelta(days=1)
        client.post(
            reverse("attendance:acrescentar", args=[marta.pk]),
            {"check_in": f"{ontem}T12:00", "check_out": f"{ontem}T16:00", "reason": "tablet sem rede"},
        )
        assert TimeEntry.objects.get(worker=marta).restaurant == casa_b


class TestFechoDoMes:
    def test_month_closes_in_the_main_house_with_all_hours(self, client, restaurant, casa_b, manager, gerente_b, marta):
        anterior = mes.previous_month(timezone.localdate())
        dia_1, dia_2 = anterior.replace(day=3), anterior.replace(day=4)
        open_shift(worker=marta, at=_quando(dia_1, 10))
        close_shift(worker=marta, at=_quando(dia_1, 14))
        open_shift(worker=marta, at=_quando(dia_2, 18), restaurant=casa_b)
        close_shift(worker=marta, at=_quando(dia_2, 23))
        _, total = mes.month_rows(marta, anterior)
        assert total == datetime.timedelta(hours=9)

        _na_casa(client, gerente_b, casa_b)
        resp = client.get(reverse("attendance:mes") + f"?mes={anterior:%Y-%m}")
        assert all(l["worker"] != marta for l in resp.context["linhas"])

        mes.approve_month(worker=marta, month=anterior, user=manager)
        csv = mes.export_csv([marta], anterior)
        assert "Casa" in csv.splitlines()[0]
        assert "Tasca da Baixa" in csv and "Tasca do Teste" in csv

    def test_unresolved_entry_in_other_house_blocks_the_month(self, restaurant, casa_b, manager, marta):
        anterior = mes.previous_month(timezone.localdate())
        open_shift(worker=marta, at=_quando(anterior.replace(day=5), 18), restaurant=casa_b)
        with pytest.raises(ValidationError, match="por resolver"):
            mes.approve_month(worker=marta, month=anterior, user=manager)


class TestTurnos:
    def _publicado(self, casa, worker, dia, inicio, fim):
        s = turnos.create_shift(restaurant=casa, worker=worker, day=dia, start=T(inicio), end=T(fim))
        s.state = Shift.State.PUBLICADO
        s.save()
        return s

    def test_overlap_across_houses_is_a_conflict(self, restaurant, casa_b, marta):
        dia = turnos.week_start(timezone.localdate()) + datetime.timedelta(days=7)
        self._publicado(restaurant, marta, dia, 9, 17)
        em_b = turnos.create_shift(restaurant=casa_b, worker=marta, day=dia, start=T(12), end=T(20))
        conflitos = turnos.conflicts(casa_b, turnos.week_start(dia))
        assert conflitos[em_b.pk] == ["Sobrepõe outro turno da mesma pessoa em Tasca do Teste"]
        # Na casa principal, só os turnos de lá ficam assinalados.
        assert all(pk != em_b.pk for pk in turnos.conflicts(restaurant, turnos.week_start(dia)))

    def test_rest_between_houses_counts(self, restaurant, casa_b, marta):
        dia = turnos.week_start(timezone.localdate()) + datetime.timedelta(days=7)
        self._publicado(restaurant, marta, dia, 18, 23)
        em_b = turnos.create_shift(restaurant=casa_b, worker=marta, day=dia + datetime.timedelta(days=1), start=T(7), end=T(12))
        motivos = turnos.conflicts(casa_b, turnos.week_start(dia))[em_b.pk]
        assert "descanso" in motivos[0] and "Tasca do Teste" in motivos[0]

    def test_rest_day_in_other_house(self, restaurant, casa_b, marta):
        dia = turnos.week_start(timezone.localdate()) + datetime.timedelta(days=7)
        turnos.set_rest_day(restaurant=restaurant, worker=marta, day=dia)
        em_b = turnos.create_shift(restaurant=casa_b, worker=marta, day=dia, start=T(12), end=T(16))
        assert "Dia de folga" in turnos.conflicts(casa_b, turnos.week_start(dia))[em_b.pk]
        with pytest.raises(ValidationError, match="já tem folga"):
            turnos.set_rest_day(restaurant=casa_b, worker=marta, day=dia)

    def test_planner_shows_shifts_of_other_house_read_only(self, client, restaurant, casa_b, gerente_b, marta):
        dia = turnos.week_start(timezone.localdate()) + datetime.timedelta(days=7)
        de_a = self._publicado(restaurant, marta, dia, 9, 13)
        _na_casa(client, gerente_b, casa_b)
        corpo = client.get(reverse("shifts:planeador") + f"?semana={dia}").content.decode()
        assert "Marta Silva" in corpo and "em Tasca do Teste" in corpo
        client.post(reverse("shifts:celula", args=[marta.pk, dia]), {"acao": "apagar", "turno": de_a.pk})
        assert Shift.objects.filter(pk=de_a.pk).exists()

    def test_cannot_plan_someone_from_another_house(self, restaurant, casa_b):
        so_a = Worker.objects.create(restaurant=restaurant, full_name="Rui Costa")
        with pytest.raises(ValidationError, match="não trabalha"):
            turnos.create_shift(restaurant=casa_b, worker=so_a, day=timezone.localdate(), start=T(9), end=T(13))


class TestFicha:
    def test_main_house_sets_other_houses(self, client, restaurant, casa_b, manager):
        rui = Worker.objects.create(restaurant=restaurant, full_name="Rui Costa")
        _na_casa(client, manager, restaurant)
        form = client.get(reverse("workers:editar", args=[rui.pk])).context["form"]
        assert list(form.fields["other_restaurants"].queryset) == [casa_b]
        client.post(
            reverse("workers:editar", args=[rui.pk]),
            {"full_name": "Rui Costa", "is_active": "on", "other_restaurants": [casa_b.pk]},
        )
        assert list(rui.other_restaurants.all()) == [casa_b]

    def test_single_house_group_has_no_field(self, client, restaurant, manager):
        _na_casa(client, manager, restaurant)
        assert "other_restaurants" not in client.get(reverse("workers:novo")).context["form"].fields

    def test_visitor_listed_in_other_house_without_edit(self, client, casa_b, gerente_b, marta):
        _na_casa(client, gerente_b, casa_b)
        corpo = client.get(reverse("workers:lista")).content.decode()
        assert "Casa principal: Tasca do Teste" in corpo
        assert reverse("workers:editar", args=[marta.pk]) not in corpo
        assert client.get(reverse("workers:editar", args=[marta.pk])).status_code == 404


class TestConsumos:
    def test_visitor_consumes_in_other_house(self, casa_b, gerente_b, marta, restaurant):
        categoria = Category.objects.get_or_create(restaurant=casa_b, name="Bebidas")[0]
        cafe = Item.objects.create(restaurant=casa_b, name="Café", category=categoria, unit=Item.Unit.UN)
        register_movement(item=cafe, movement_type=StockMovement.Type.ENTRADA, quantity=Decimal("10"), user=gerente_b)
        consumo = register_consumption(
            restaurant=casa_b, worker=marta, reason=InternalConsumption.Reason.OFERTA,
            day=timezone.localdate(), lines=[(cafe, Decimal("1"))], user=gerente_b,
        )
        assert consumo.restaurant == casa_b
        so_a = Worker.objects.create(restaurant=restaurant, full_name="Rui Costa")
        with pytest.raises(ValidationError, match="não trabalha"):
            register_consumption(
                restaurant=casa_b, worker=so_a, reason=InternalConsumption.Reason.OFERTA,
                day=timezone.localdate(), lines=[(cafe, Decimal("1"))], user=gerente_b,
            )
