"""
Dados de demonstração (Fase 4): restaurante, os quatro perfis, equipa,
stock com movimentos, ponto e férias — o suficiente para o percurso
completo de cada perfil. Idempotente: correr duas vezes não duplica.

    python manage.py demo

Contas criadas (password de todas: demo1234):
    admin@tasca.pt · gerente@tasca.pt · stock@tasca.pt · marta@tasca.pt
PIN da Marta (vista staff): 2468
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from attendance.services import add_manual_entry, open_shift
from core.models import Restaurant
from inventory.models import Category, Item
from inventory.services import register_movement
from vacations.models import VacationRequest
from vacations.services import decide_request
from workers.models import Worker

User = get_user_model()
PASSWORD = "demo1234"


class Command(BaseCommand):
    help = "Cria dados de demonstração para o percurso dos quatro perfis."

    def handle(self, *args, **options):
        restaurant, criado = Restaurant.objects.get_or_create(
            slug="tasca-da-esquina", defaults={"name": "Tasca da Esquina"}
        )
        if not criado:
            self.stdout.write("Restaurante já existe — a reutilizar (comando idempotente).")

        def utilizador(email, role, first, last):
            user, novo = User.objects.get_or_create(
                email=email,
                defaults={"role": role, "restaurant": restaurant, "first_name": first, "last_name": last},
            )
            if novo:
                user.set_password(PASSWORD)
                user.save()
            return user

        admin = utilizador("admin@tasca.pt", User.Role.ADMIN, "Alice", "Torres")
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()
        gerente = utilizador("gerente@tasca.pt", User.Role.MANAGER, "Gustavo", "Reis")
        resp_stock = utilizador("stock@tasca.pt", User.Role.STOCK, "Rui", "Gomes")
        marta_user = utilizador("marta@tasca.pt", User.Role.STAFF, "Marta", "Silva")
        if not marta_user.has_pin:
            marta_user.set_staff_pin("2468")

        def trabalhador(nome, funcao, user=None):
            w, _ = Worker.objects.get_or_create(
                restaurant=restaurant, full_name=nome, defaults={"job_title": funcao, "user": user}
            )
            return w

        marta = trabalhador("Marta Silva", "sala", marta_user)
        rui = trabalhador("Rui Gomes", "responsável de stock", resp_stock)
        joao = trabalhador("João Duarte", "cozinha")
        trabalhador("Beatriz Nunes", "copa")

        categorias = {c.name: c for c in Category.objects.filter(restaurant=restaurant)}
        artigos = [
            ("Tomate chucha", "Frescos", Item.Unit.KG, "10", "34.5"),
            ("Azeite virgem extra", "Mercearia", Item.Unit.L, "6", "2"),
            ("Vinho tinto da casa", "Bebidas", Item.Unit.UN, "12", "48"),
            ("Guardanapos 33x33", "Embalagem", Item.Unit.EMB, "5", "18"),
            ("Lixívia alimentar", "Limpeza", Item.Unit.L, "2", "0"),
        ]
        agora = timezone.now()
        for nome, cat, unidade, minimo, stock in artigos:
            item, novo = Item.objects.get_or_create(
                restaurant=restaurant,
                name=nome,
                defaults={
                    "category": categorias[cat],
                    "unit": unidade,
                    "minimum_stock": Decimal(minimo),
                },
            )
            if novo and Decimal(stock) > 0:
                register_movement(
                    item=item,
                    movement_type="ENTRADA",
                    quantity=Decimal(stock),
                    user=resp_stock,
                    occurred_at=agora - datetime.timedelta(days=2),
                    reason="stock inicial de demonstração",
                )
        tomate = Item.objects.get(restaurant=restaurant, name="Tomate chucha")
        if tomate.movements.count() == 1:
            register_movement(
                item=tomate,
                movement_type="SAIDA",
                quantity=Decimal("4.5"),
                user=resp_stock,
                occurred_at=agora - datetime.timedelta(hours=5),
                reason="consumo do serviço de almoço",
            )

        if not marta.time_entries.exists():
            ontem = agora - datetime.timedelta(days=1)
            add_manual_entry(
                worker=marta,
                user=gerente,
                reason="registo de demonstração",
                check_in=ontem.replace(hour=9, minute=2),
                check_out=ontem.replace(hour=17, minute=31),
            )
        if joao.open_entry is None:
            open_shift(worker=joao, at=agora - datetime.timedelta(hours=3))

        if not VacationRequest.objects.filter(worker=marta).exists():
            aprovado = VacationRequest.objects.create(
                worker=marta,
                start_date=datetime.date.today() + datetime.timedelta(days=30),
                end_date=datetime.date.today() + datetime.timedelta(days=37),
                request_note="viagem em família",
            )
            decide_request(request_obj=aprovado, user=gerente, approve=True, note="boas férias")
            VacationRequest.objects.create(
                worker=marta,
                start_date=datetime.date.today() + datetime.timedelta(days=35),
                end_date=datetime.date.today() + datetime.timedelta(days=40),
                request_note="prolongar a viagem",
            )
        if not VacationRequest.objects.filter(worker=rui).exists():
            VacationRequest.objects.create(
                worker=rui,
                start_date=datetime.date.today() + datetime.timedelta(days=14),
                end_date=datetime.date.today() + datetime.timedelta(days=18),
            )

        self.stdout.write(self.style.SUCCESS("Dados de demonstração prontos."))
        self.stdout.write(f"Contas (password {PASSWORD}): admin@tasca.pt, gerente@tasca.pt, stock@tasca.pt, marta@tasca.pt")
        self.stdout.write("PIN da Marta: 2468 (ativar o dispositivo em Configuracao > Dispositivo)")
