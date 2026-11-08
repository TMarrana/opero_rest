"""Ficha do trabalhador (2026-11-04): sem «Conta de acesso» no formulário,
função, contacto e data de início obrigatórios, emails únicos, e apagar
uma ficha sem histórico."""
import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.urls import reverse
from django.utils import timezone

from attendance.models import CorrectionRequest
from attendance.services import add_manual_entry, annul_entry, open_shift
from core.models import Restaurant
from inventory import consumption
from inventory.models import Category, InternalConsumption, Item, StockMovement
from inventory.services import register_movement
from workers.formatos import normalizar_contacto
from workers.models import Worker
from workers.services import delete_blockers, delete_worker

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.mark.parametrize("entrada,saida", [
    ("965852489", "+351 965 852 489"), ("+351911043974", "+351 911 043 974"),
    ("00351 910 161 333", "+351 910 161 333"), ("+44 20 7946 0958", "+44 20 7946 0958"),
    (" ana@mail.pt ", "ana@mail.pt"),
])
def test_normalizar_contacto(entrada, saida):
    assert normalizar_contacto(entrada) == saida


def test_migracao_arruma_as_fichas_que_ja_existem(restaurant):
    from importlib import import_module

    from django.apps import apps

    antiga = Worker.objects.create(restaurant=restaurant, full_name="Rui Sousa", job_title="copeiro", contact="965852489")
    sem_nada = Worker.objects.create(restaurant=restaurant, full_name="Ana Lopes")
    import_module("workers.migrations.0005_funcao_e_contacto_arrumados").arrumar_fichas(apps, None)
    antiga.refresh_from_db()
    sem_nada.refresh_from_db()
    assert (antiga.job_title, antiga.contact) == ("Copeiro", "+351 965 852 489")
    assert (sem_nada.job_title, sem_nada.contact) == ("", "")

H = datetime.timedelta(hours=1)
FICHA = {"full_name": "Ana Lopes", "job_title": "Sala", "contact": "912345678", "start_date": "2026-01-05", "is_active": "on"}


class TestFormulario:
    def test_sem_conta_de_acesso(self, client, manager):
        client.force_login(manager)
        resp = client.get(reverse("workers:novo"))
        assert "user" not in resp.context["form"].fields
        assert "Conta de acesso" not in resp.content.decode()

    def test_campos_obrigatorios(self, client, restaurant, manager):
        client.force_login(manager)
        resp = client.post(reverse("workers:novo"), {"full_name": "Ana Lopes", "is_active": "on"})
        html = resp.content.decode()
        assert resp.status_code == 200 and not Worker.objects.exists()
        assert "Indique a função." in html
        assert "Indique um contacto" in html
        assert "Indique a data de início." in html
        resp = client.post(reverse("workers:novo"), FICHA)
        assert resp.status_code == 302
        ana = Worker.objects.get()
        assert (ana.job_title, ana.contact, ana.start_date) == ("Sala", "+351 912 345 678", datetime.date(2026, 1, 5))

    def test_funcao_com_maiuscula_e_telefone_no_formato_351(self, client, restaurant, manager):
        client.force_login(manager)
        client.post(reverse("workers:novo"), {**FICHA, "job_title": " copeiro ", "contact": "00351 965852489"})
        ana = Worker.objects.get()
        assert (ana.job_title, ana.contact) == ("Copeiro", "+351 965 852 489")

    def test_post_com_user_nao_liga_conta(self, client, restaurant, manager, staff_user):
        """Mesmo enviando `user` à mão, a ficha não fica ligada a uma conta."""
        client.force_login(manager)
        client.post(reverse("workers:novo"), {**FICHA, "user": staff_user.pk})
        assert Worker.objects.get().user is None

    def test_email_repetido_recusado_mesmo_com_maiusculas(self, client, restaurant, manager, staff_user):
        ana = Worker.objects.create(restaurant=restaurant, full_name="Ana Lopes")
        client.force_login(manager)
        resp = client.post(
            reverse("workers:conta", args=[ana.pk]), {"acao": "criar", "email": staff_user.email.upper(), "role": "STAFF"}
        )
        assert "Cada conta é de uma só pessoa" in resp.content.decode()
        ana.refresh_from_db()
        assert ana.user is None


class TestApagar:
    def test_apaga_ficha_sem_historico_e_a_conta(self, client, restaurant, manager, staff_user):
        ana = Worker.objects.create(restaurant=restaurant, full_name="Ana Lopes", user=staff_user)
        client.force_login(manager)
        html = client.get(reverse("workers:editar", args=[ana.pk])).content.decode()
        assert 'title="Eliminar trabalhador"' in html and reverse("workers:apagar", args=[ana.pk]) in html
        assert "Tem a certeza?" in html and ">Eliminar</button>" in html
        resp = client.post(reverse("workers:apagar", args=[ana.pk]))
        assert resp.status_code == 302 and resp.url == reverse("workers:lista")
        assert not Worker.objects.filter(pk=ana.pk).exists()
        assert not User.objects.filter(pk=staff_user.pk).exists()

    def test_com_ponto_nao_se_apaga(self, client, restaurant, manager):
        ana = Worker.objects.create(restaurant=restaurant, full_name="Ana Lopes")
        open_shift(worker=ana)
        client.force_login(manager)
        html = client.get(reverse("workers:editar", args=[ana.pk])).content.decode()
        assert 'title="Eliminar trabalhador"' in html
        assert "Não é possível eliminar" in html and "1 registo de ponto" in html
        assert reverse("workers:desativar", args=[ana.pk]) in html and ">Desativar</button>" in html
        assert reverse("workers:apagar", args=[ana.pk]) not in html
        resp = client.post(reverse("workers:apagar", args=[ana.pk]), follow=True)
        assert "Desative a ficha" in resp.content.decode()
        assert Worker.objects.filter(pk=ana.pk).exists()
        # Desativar pelo aviso.
        resp = client.post(reverse("workers:desativar", args=[ana.pk]))
        assert resp.status_code == 302
        ana.refresh_from_db()
        assert ana.is_active is False
        html = client.get(reverse("workers:editar", args=[ana.pk])).content.decode()
        assert "Já está desativado." in html and reverse("workers:desativar", args=[ana.pk]) not in html

    def test_com_consumo_nao_se_apaga(self, client, restaurant, manager):
        ana = Worker.objects.create(restaurant=restaurant, full_name="Ana Lopes")
        categoria = Category.objects.get_or_create(restaurant=restaurant, name="Bebidas")[0]
        cafe = Item.objects.create(restaurant=restaurant, name="Café", category=categoria, unit=Item.Unit.UN)
        register_movement(item=cafe, movement_type=StockMovement.Type.ENTRADA, quantity=Decimal(5), user=manager)
        consumption.register_consumption(
            restaurant=restaurant, worker=ana, reason=InternalConsumption.Reason.REFEICAO,
            day=timezone.localdate(), lines=[(cafe, Decimal(1))], user=manager,
        )
        client.force_login(manager)
        client.post(reverse("workers:apagar", args=[ana.pk]))
        assert Worker.objects.filter(pk=ana.pk).exists()

    def test_conta_que_registou_coisas_fica_desativada(self, client, restaurant, manager, stock_user):
        rui = Worker.objects.create(restaurant=restaurant, full_name="Rui Gomes", user=stock_user)
        categoria = Category.objects.get_or_create(restaurant=restaurant, name="Bebidas")[0]
        cafe = Item.objects.create(restaurant=restaurant, name="Café", category=categoria, unit=Item.Unit.UN)
        register_movement(item=cafe, movement_type=StockMovement.Type.ENTRADA, quantity=Decimal(5), user=stock_user)
        client.force_login(manager)
        client.post(reverse("workers:apagar", args=[rui.pk]))
        assert not Worker.objects.filter(pk=rui.pk).exists()
        stock_user.refresh_from_db()
        assert stock_user.is_active is False

    def test_gerente_nao_apaga_conta_de_gerente_nem_a_sua(self, client, restaurant, manager, admin_user):
        do_admin = Worker.objects.create(restaurant=restaurant, full_name="Dona", user=admin_user)
        propria = Worker.objects.create(restaurant=restaurant, full_name="Gerente", user=manager)
        client.force_login(manager)
        client.post(reverse("workers:apagar", args=[do_admin.pk]))
        client.post(reverse("workers:apagar", args=[propria.pk]))
        assert Worker.objects.filter(pk__in=[do_admin.pk, propria.pk]).count() == 2
        assert "Esta é a sua ficha" in client.get(reverse("workers:editar", args=[propria.pk])).content.decode()
        assert "só o administrador a pode eliminar" in client.get(reverse("workers:editar", args=[do_admin.pk])).content.decode()

    def test_colaborador_nao_apaga(self, client, restaurant, staff_user):
        ana = Worker.objects.create(restaurant=restaurant, full_name="Ana Lopes")
        client.force_login(staff_user)
        assert client.post(reverse("workers:apagar", args=[ana.pk])).status_code == 403
        assert client.post(reverse("workers:desativar", args=[ana.pk])).status_code == 403
        ana.refresh_from_db()
        assert ana.is_active


class TestRegistosProtegidos:
    """Os registos com valor legal não se apagam em cascata, nem por código."""

    def test_ficha_com_registos_nao_se_apaga_nem_por_codigo(self, restaurant, manager):
        w = Worker.objects.create(restaurant=restaurant, full_name="Rui Registo")
        agora = timezone.now()
        add_manual_entry(worker=w, user=manager, check_in=agora - 3 * H, check_out=agora - H)
        with pytest.raises(ProtectedError):
            w.delete()

    def test_casa_com_registos_nao_se_apaga(self):
        # Nenhuma conta aponta para a casa: só o registo de ponto a protege.
        casa = Restaurant.objects.create(name="Casa Protegida", slug="casa-protegida")
        outra = Restaurant.objects.create(name="Outra Casa", slug="outra-casa")
        gerente = User.objects.create_user(
            email="gerente@outra.pt", password="segredo-de-teste-123", restaurant=outra, role=User.Role.MANAGER
        )
        w = Worker.objects.create(restaurant=casa, full_name="Rui Registo")
        agora = timezone.now()
        add_manual_entry(worker=w, user=gerente, check_in=agora - 3 * H, check_out=agora - H)
        with pytest.raises(ProtectedError):
            casa.delete()

    def test_registo_apagado_tambem_impede_apagar_a_ficha(self, restaurant, manager):
        w = Worker.objects.create(restaurant=restaurant, full_name="Rui Registo")
        agora = timezone.now()
        entrada = add_manual_entry(worker=w, user=manager, check_in=agora - 3 * H, check_out=agora - H)
        annul_entry(entry=entrada, user=manager, reason="engano")
        assert not w.time_entries.exists()  # fora das listas, mas guardado
        assert delete_blockers(w) == ["1 registo de ponto"]
        with pytest.raises(ValidationError):
            delete_worker(worker=w, user=manager)
        assert Worker.objects.filter(pk=w.pk).exists()

    def test_pedido_de_correcao_sem_registo_impede_apagar_a_ficha(self, restaurant, manager):
        """Um pedido de acrescentar registo não cria registo de ponto, mas a
        ficha tem de ficar guardada na mesma."""
        w = Worker.objects.create(restaurant=restaurant, full_name="Rui Registo")
        agora = timezone.now()
        CorrectionRequest.objects.create(
            worker=w, restaurant=restaurant, kind=CorrectionRequest.Kind.CRIAR,
            new_check_in=agora - 3 * H, new_check_out=agora - H, note="esqueci-me de picar",
        )
        with pytest.raises(ValidationError):
            delete_worker(worker=w, user=manager)
        assert delete_blockers(w) == ["1 pedido de correção"]
        assert Worker.objects.filter(pk=w.pk).exists()


@pytest.mark.parametrize("modelo,campo", [
    ("attendance.TimeEntry", "worker"), ("attendance.TimeEntry", "restaurant"),
    ("attendance.CorrectionRequest", "worker"), ("attendance.CorrectionRequest", "restaurant"),
    ("attendance.MonthClose", "worker"), ("attendance.MonthClose", "restaurant"),
    ("inventory.InternalConsumption", "restaurant"), ("purchasing.Receipt", "restaurant"),
    ("sales.SalesImport", "restaurant"), ("sales.SalesDocument", "restaurant"),
    ("vacations.VacationRequest", "worker"),
])
def test_registos_legais_estao_protegidos_contra_cascata(modelo, campo):
    from django.apps import apps
    from django.db.models import PROTECT

    assert apps.get_model(modelo)._meta.get_field(campo).remote_field.on_delete is PROTECT


def test_apagar_ficha_com_historico_inesperado_da_mensagem_e_nao_500(restaurant, manager, monkeypatch):
    """Um PROTECT novo que o delete_blockers ainda nao conhece: a ficha fica
    e o gerente recebe a mensagem de sempre, nao um erro 500."""
    import workers.services as servicos

    w = Worker.objects.create(restaurant=restaurant, full_name="Rui Novo")
    monkeypatch.setattr(servicos, "delete_blockers", lambda worker: [])

    def recusa(*a, **k):
        raise ProtectedError("protegido", set())

    monkeypatch.setattr(Worker, "delete", recusa)
    with pytest.raises(ValidationError, match="Desative a ficha"):
        delete_worker(worker=w, user=manager)
