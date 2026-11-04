"""Ficha do trabalhador (2026-11-04): sem «Conta de acesso» no formulário,
função, contacto e data de início obrigatórios, emails únicos, e apagar
uma ficha sem histórico."""
import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from attendance.services import open_shift
from inventory import consumption
from inventory.models import Category, InternalConsumption, Item, StockMovement
from inventory.services import register_movement
from workers.models import Worker

pytestmark = pytest.mark.django_db
User = get_user_model()

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
        assert (ana.job_title, ana.contact, ana.start_date) == ("Sala", "912345678", datetime.date(2026, 1, 5))

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
