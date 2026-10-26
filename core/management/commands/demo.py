"""
Dados de demonstração (Fase 4): restaurante, os quatro perfis, equipa,
stock com movimentos, ponto e férias — o suficiente para o percurso
completo de cada perfil. Idempotente: correr duas vezes não duplica.

    python manage.py demo

Contas criadas (password de todas: demo1234):
    admin@tasca.pt · gerente@tasca.pt · stock@tasca.pt · marta@tasca.pt
    dono@tasca.pt (Admin do grupo, Fase 9)
Códigos de ponto no quiosque (/quiosque/, Fase 7):
    Marta 2468 · Rui 1122 · Gustavo (gerente) 1357 · Inês (Ribeira) 4321

Fase 9: duas casas no mesmo grupo, a Tasca da Esquina e a Tasca da
Ribeira. O gerente tem acesso às duas.
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from attendance.services import add_manual_entry, open_shift
from accounts.services import dar_acesso
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

        def trabalhador(nome, funcao, user=None):
            # Uma conta que já tem ficha (por exemplo, ligada à mão) fica com ela.
            if user is not None and Worker.objects.filter(user=user).exists():
                return user.worker
            w, _ = Worker.objects.get_or_create(
                restaurant=restaurant, full_name=nome, defaults={"job_title": funcao, "user": user}
            )
            return w

        marta = trabalhador("Marta Silva", "sala", marta_user)
        rui = trabalhador("Rui Gomes", "responsável de stock", resp_stock)
        gustavo = trabalhador("Gustavo Reis", "gerente", gerente)
        joao = trabalhador("João Duarte", "cozinha")
        trabalhador("Beatriz Nunes", "copa")
        # Gerentes e responsáveis de stock também picam no tablet (Fase 7).
        for w, codigo in [(marta, "2468"), (rui, "1122"), (gustavo, "1357")]:
            if not w.has_code:
                w.set_kiosk_code(codigo)

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

        self._segunda_casa(restaurant, gerente)

        self.stdout.write(self.style.SUCCESS("Dados de demonstração prontos."))
        self.stdout.write(
            f"Contas (password {PASSWORD}): admin@tasca.pt, gerente@tasca.pt, stock@tasca.pt, marta@tasca.pt, "
            "dono@tasca.pt (Admin do grupo)"
        )
        self.stdout.write(
            "Codigos de ponto: Marta 2468, Rui 1122, Gustavo 1357, Ines 4321 na Ribeira "
            "(ativar o tablet em Dispositivo e abrir /quiosque/)"
        )

    def _segunda_casa(self, esquina, gerente):
        """Fase 9: a segunda casa do grupo, o Admin do grupo e o gerente com
        acesso às duas."""
        grupo = esquina.organization
        if grupo.name == esquina.name:
            grupo.name = "Grupo Tasca"
            grupo.save(update_fields=["name", "updated_at"])
        ribeira, _ = Restaurant.objects.get_or_create(
            slug="tasca-da-ribeira", defaults={"name": "Tasca da Ribeira", "organization": grupo, "municipality": "Porto"}
        )
        dono, novo = User.objects.get_or_create(
            email="dono@tasca.pt",
            defaults={"first_name": "Dora", "last_name": "Lima", "organization": grupo, "is_group_admin": True},
        )
        if novo:
            dono.set_password(PASSWORD)
            dono.save()
        dar_acesso(gerente, ribeira, User.Role.MANAGER)

        ines, _ = Worker.objects.get_or_create(restaurant=ribeira, full_name="Inês Rocha", defaults={"job_title": "sala"})
        if not ines.has_code:
            ines.set_kiosk_code("4321")
        Worker.objects.get_or_create(restaurant=ribeira, full_name="Paulo Freitas", defaults={"job_title": "cozinha"})

        categorias = {c.name: c for c in Category.objects.filter(restaurant=ribeira)}
        for nome, cat, unidade, minimo, stock in [
            ("Tomate chucha", "Frescos", Item.Unit.KG, "5", "2"),
            ("Arroz carolino", "Mercearia", Item.Unit.KG, "10", "25"),
            ("Vinho tinto da casa", "Bebidas", Item.Unit.UN, "12", "30"),
        ]:
            item, novo = Item.objects.get_or_create(
                restaurant=ribeira,
                name=nome,
                defaults={"category": categorias[cat], "unit": unidade, "minimum_stock": Decimal(minimo)},
            )
            if novo:
                register_movement(
                    item=item,
                    movement_type="ENTRADA",
                    quantity=Decimal(stock),
                    user=gerente,
                    reason="stock inicial de demonstração",
                )
