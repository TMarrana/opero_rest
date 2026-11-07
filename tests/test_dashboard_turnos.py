"""Dashboard (2026-11-04): o card «Turnos de hoje» mostra os turnos
publicados do dia com quem já picou, quem está em turno e quem falta."""
import datetime
from types import SimpleNamespace

import pytest
from django.urls import reverse
from django.utils import timezone

from attendance.services import close_shift, open_shift
from dashboard.views import saudacao, turnos_de_hoje
from sales.services import dia_de_servico
from shifts.models import Shift
from shifts.services import create_shift
from workers.models import Worker

pytestmark = pytest.mark.django_db

HOJE = datetime.date(2026, 11, 4)


def hora(h, m=0):
    return timezone.make_aware(datetime.datetime.combine(HOJE, datetime.time(h, m)))


def turno(restaurant, worker, inicio, fim, estado=Shift.State.PUBLICADO, dia=HOJE):
    t = create_shift(restaurant=restaurant, worker=worker, day=dia, start=inicio, end=fim)
    t.state = estado
    t.save()
    return t


@pytest.fixture
def equipa(restaurant):
    nomes = ["Ana", "Bruno", "Carla", "Duarte", "Eva"]
    return {n: Worker.objects.create(restaurant=restaurant, full_name=n) for n in nomes}


def test_estados(restaurant, equipa):
    pedido = SimpleNamespace(restaurant=restaurant)
    turno(restaurant, equipa["Ana"], datetime.time(9), datetime.time(15))  # em turno, atrasada
    turno(restaurant, equipa["Bruno"], datetime.time(8), datetime.time(12))  # já saiu
    turno(restaurant, equipa["Carla"], datetime.time(10), datetime.time(16))  # em falta
    turno(restaurant, equipa["Duarte"], datetime.time(19), datetime.time(23))  # por entrar
    turno(restaurant, equipa["Duarte"], datetime.time(12), datetime.time(13), estado=Shift.State.RASCUNHO)
    open_shift(worker=equipa["Ana"], at=hora(9, 20))
    open_shift(worker=equipa["Bruno"], at=hora(7, 58))
    close_shift(worker=equipa["Bruno"], at=hora(12, 2))
    open_shift(worker=equipa["Eva"], at=hora(11))  # sem turno

    r = turnos_de_hoje(pedido, agora=hora(12, 30))
    estados = {l["worker"].full_name: l["estado"] for l in r["turnos_hoje"]}
    assert estados == {"Ana": "em_turno", "Bruno": "saiu", "Carla": "em_falta", "Duarte": "por_entrar", "Eva": "sem_turno"}
    assert [l["worker"].full_name for l in r["turnos_hoje"]] == ["Bruno", "Ana", "Carla", "Duarte", "Eva"]
    assert (r["turnos_previstos"], r["turnos_picaram"], r["turnos_em_falta"]) == (4, 2, 1)
    ana = next(l for l in r["turnos_hoje"] if l["worker"].full_name == "Ana")
    assert ana["desvios"] == ["Entrou 20 min depois"]
    duarte = next(l for l in r["turnos_hoje"] if l["worker"].full_name == "Duarte")
    assert len(duarte["turnos"]) == 1  # o rascunho não conta


def test_linha_do_tempo(restaurant, equipa):
    """A escala vai da hora cheia antes do primeiro turno à hora cheia depois
    do último; as barras em percentagem, com ponto decimal."""
    turno(restaurant, equipa["Ana"], datetime.time(10), datetime.time(14))
    turno(restaurant, equipa["Bruno"], datetime.time(19), datetime.time(1))  # passa a meia-noite
    open_shift(worker=equipa["Ana"], at=hora(10, 30))
    r = turnos_de_hoje(SimpleNamespace(restaurant=restaurant), agora=hora(12))
    escala = r["escala"]
    assert escala["horas"][0] == {"hora": "10h", "pos": "0.00", "oculta": False}
    # Das 10h à 1h da noite (15 h): marcas de 2 em 2 horas, a última à meia-noite.
    assert [h["hora"] for h in escala["horas"]] == ["10h", "12h", "14h", "16h", "18h", "20h", "22h", "00h"]
    assert escala["agora"] == "13.33" and escala["agora_txt"] == "12:00"
    ana = next(l for l in r["turnos_hoje"] if l["worker"].full_name == "Ana")
    assert ana["barras_turno"][0]["esquerda"] == "0.00" and ana["barras_turno"][0]["largura"] == "26.67"
    assert ana["barras_ponto"] == [{"esquerda": "3.33", "largura": "10.00", "aberto": True}]
    bruno = next(l for l in r["turnos_hoje"] if l["worker"].full_name == "Bruno")
    assert bruno["barras_turno"][0]["esquerda"] == "60.00" and bruno["barras_turno"][0]["largura"] == "40.00"


def test_dentro_da_tolerancia_ainda_nao_falta(restaurant, equipa):
    turno(restaurant, equipa["Carla"], datetime.time(10), datetime.time(16))
    r = turnos_de_hoje(SimpleNamespace(restaurant=restaurant), agora=hora(10, 5))
    assert r["turnos_hoje"][0]["estado"] == "por_entrar" and r["turnos_em_falta"] == 0


def test_so_os_turnos_desta_casa(restaurant, equipa):
    from core.models import Restaurant

    outra = Restaurant.objects.create(name="Outra casa", slug="outra-casa")
    estranho = Worker.objects.create(restaurant=outra, full_name="Zé")
    turno(outra, estranho, datetime.time(10), datetime.time(16))
    r = turnos_de_hoje(SimpleNamespace(restaurant=restaurant), agora=hora(12))
    assert r["turnos_hoje"] == []


SEXTA = datetime.date(2026, 11, 6)
SABADO = datetime.date(2026, 11, 7)


def _sabado(h, m):
    return timezone.make_aware(datetime.datetime(2026, 11, 7, h, m))


def test_de_madrugada_mostra_o_servico_da_noite(restaurant, equipa):
    turno(restaurant, equipa["Ana"], datetime.time(20), datetime.time(2), dia=SEXTA)
    r = turnos_de_hoje(SimpleNamespace(restaurant=restaurant), agora=_sabado(1, 30))
    assert [l["worker"] for l in r["turnos_hoje"]] == [equipa["Ana"]]


def test_etiqueta_agora_esconde_a_hora_por_baixo(restaurant, equipa):
    # Escala das 11h às 26h (02h de sábado), de 2 em 2 horas: «01h» fica a 93,3%
    # e a hora atual (01:21) a 95,7%, a menos de 4 pontos.
    turno(restaurant, equipa["Ana"], datetime.time(11), datetime.time(16), dia=SEXTA)
    turno(restaurant, equipa["Bruno"], datetime.time(20), datetime.time(2), dia=SEXTA)
    r = turnos_de_hoje(SimpleNamespace(restaurant=restaurant), agora=_sabado(1, 21))
    horas = {h["hora"]: h["oculta"] for h in r["escala"]["horas"]}
    assert horas["01h"] is True and horas["23h"] is False


def test_sem_marcador_agora_nenhuma_hora_fica_oculta(restaurant, equipa):
    # Às 03h de sábado a escala de sexta (10h–24h) já não chega à hora atual.
    turno(restaurant, equipa["Ana"], datetime.time(10), datetime.time(14), dia=SEXTA)
    r = turnos_de_hoje(SimpleNamespace(restaurant=restaurant), agora=_sabado(3, 0))
    assert r["escala"]["agora"] is None
    assert not any(h["oculta"] for h in r["escala"]["horas"])


@pytest.mark.parametrize("h,texto", [(1, "Boa noite"), (4, "Boa noite"), (5, "Bom dia"), (9, "Bom dia"),
                                     (12, "Boa tarde"), (15, "Boa tarde"), (19, "Boa tarde"), (20, "Boa noite"), (21, "Boa noite")])
def test_saudacao(h, texto):
    assert saudacao(h) == texto


def test_dia_de_servico_de_madrugada_e_o_dia_anterior(restaurant):
    assert dia_de_servico(restaurant, agora=_sabado(1, 30)) == SEXTA


def test_dia_de_servico_depois_do_corte_e_o_proprio_dia(restaurant):
    assert dia_de_servico(restaurant, agora=_sabado(5, 0)) == SABADO


class TestCard:
    def test_gerente_ve_o_card(self, client, restaurant, manager, equipa):
        hoje = dia_de_servico(restaurant)
        turno(restaurant, equipa["Carla"], datetime.time(0, 1), datetime.time(23, 59), dia=hoje)
        client.force_login(manager)
        html = client.get(reverse("dashboard:home")).content.decode()
        assert "Turnos de hoje" in html and "Carla" in html
        assert "0</span> de <span class=\"font-dados\">1</span> já picaram" in html

    def test_sem_turnos(self, client, manager):
        client.force_login(manager)
        assert "Não há turnos publicados para hoje." in client.get(reverse("dashboard:home")).content.decode()

    def test_stock_nao_ve(self, client, stock_user):
        client.force_login(stock_user)
        assert "Turnos de hoje" not in client.get(reverse("dashboard:home")).content.decode()


class TestDesviosPorTurno:
    """Cada registo compara-se com o turno com que coincide (2026-11-04)."""

    def test_segundo_registo_fora_do_turno(self, restaurant, equipa, manager):
        from attendance.desvios import textos
        from attendance.services import add_manual_entry

        t = turno(restaurant, equipa["Ana"], datetime.time(11), datetime.time(16))
        r1 = add_manual_entry(worker=equipa["Ana"], user=manager, check_in=hora(9), check_out=hora(17, 30))
        r2 = add_manual_entry(worker=equipa["Ana"], user=manager, check_in=hora(19), check_out=hora(21, 20))
        assert textos([t], [r1, r2], hora(22)) == ["Entrou 2h mais cedo", "Saiu 1h30 depois", "Fora do turno: 19:00–21:20"]

    def test_dois_turnos_cada_um_com_o_seu(self, restaurant, equipa, manager):
        from attendance.desvios import textos
        from attendance.services import add_manual_entry

        almoco = turno(restaurant, equipa["Ana"], datetime.time(11), datetime.time(15))
        jantar = turno(restaurant, equipa["Ana"], datetime.time(19), datetime.time(23))
        r1 = add_manual_entry(worker=equipa["Ana"], user=manager, check_in=hora(11, 2), check_out=hora(15))
        r2 = add_manual_entry(worker=equipa["Ana"], user=manager, check_in=hora(19, 30), check_out=hora(22))
        assert textos([almoco, jantar], [r1, r2], hora(23, 30)) == [
            "Entrou 30 min depois (turno das 19:00)",
            "Saiu 1h antes (turno das 19:00)",
        ]
        assert textos([almoco, jantar], [r1], hora(23, 30)) == ["Sem marcação (turno das 19:00)"]

    def test_dentro_da_tolerancia_nada(self, restaurant, equipa, manager):
        from attendance.desvios import textos
        from attendance.services import add_manual_entry

        t = turno(restaurant, equipa["Ana"], datetime.time(11), datetime.time(16))
        r = add_manual_entry(worker=equipa["Ana"], user=manager, check_in=hora(10, 55), check_out=hora(16, 8))
        assert textos([t], [r], hora(17)) == []
