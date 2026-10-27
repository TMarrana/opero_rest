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

        ribeira = self._segunda_casa(restaurant, gerente)
        self._vendas(restaurant, ribeira, gerente)
        self._compras(restaurant, resp_stock)
        self._consumos(restaurant, gerente, [marta, rui])
        self._fichas(restaurant, ribeira, gerente)

        self.stdout.write(self.style.SUCCESS("Dados de demonstração prontos."))
        self.stdout.write(
            f"Contas (password {PASSWORD}): admin@tasca.pt, gerente@tasca.pt, stock@tasca.pt, marta@tasca.pt, "
            "dono@tasca.pt (Admin do grupo)"
        )
        self.stdout.write(
            "Codigos de ponto: Marta 2468, Rui 1122, Gustavo 1357, Ines 4321 na Ribeira e na Esquina "
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
        # A Inês é da Ribeira e faz jantares na Esquina (Fase 9).
        ines.other_restaurants.add(esquina)
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
        return ribeira

    def _vendas(self, esquina, ribeira, gerente):
        """Fase 10: um SAF-T sintético de cada casa, do dia 1 do mês passado
        até ontem, importado como o gerente o faria."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        from sales import sintetico
        from sales.models import SalesImport
        from sales.services import import_saft

        ontem = timezone.localdate() - datetime.timedelta(days=1)
        inicio = (ontem.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
        for casa, nif, serie, semente in ((esquina, "509123457", "E", 1), (ribeira, "510000002", "R", 2)):
            if not casa.nif:
                casa.nif = nif
                casa.save(update_fields=["nif", "updated_at"])
            if SalesImport.objects.filter(restaurant=casa).exists():
                continue
            docs = sintetico.mes_de_demonstracao(inicio=inicio, fim=ontem, serie=serie, semente=semente)
            conteudo = sintetico.gerar(nif=casa.nif, documentos=docs, inicio=inicio, fim=ontem)
            imp = import_saft(
                restaurant=casa, upload=SimpleUploadedFile(f"saft-{casa.slug}.xml", conteudo), user=gerente
            )
            self.stdout.write(f"Vendas de {casa.slug}: {imp.documents_new} documentos importados")

    def _compras(self, esquina, resp_stock):
        """Fase 11: três fornecedores do grupo, os preferidos dos artigos da
        Esquina, dois frescos abaixo do mínimo e uma receção da semana
        passada, para haver histórico de preços."""
        from purchasing.models import Receipt, Supplier
        from purchasing.services import receive, save_supplier_item

        grupo = esquina.organization
        frescos, _ = Supplier.objects.get_or_create(
            organization=grupo, name="Frescos do Mercado",
            defaults={"contact_name": "Sr. Albino", "phone": "912 345 678", "delivery_days": "1,4",
                      "notes": "Encomendar até às 18h da véspera."},
        )
        mercearia, _ = Supplier.objects.get_or_create(
            organization=grupo, name="Mercearia Central",
            defaults={"nif": "505000008", "email": "encomendas@merceariacentral.pt", "delivery_days": "2"},
        )
        drogaria, _ = Supplier.objects.get_or_create(organization=grupo, name="Drogaria Lopes", defaults={"delivery_days": "3"})

        categorias = {c.name: c for c in Category.objects.filter(restaurant=esquina)}
        for nome, minimo, stock in [("Alface frisada", "4", "1"), ("Cebola", "8", "3")]:
            item, novo = Item.objects.get_or_create(
                restaurant=esquina, name=nome,
                defaults={"category": categorias["Frescos"], "unit": Item.Unit.KG, "minimum_stock": Decimal(minimo)},
            )
            if novo:
                register_movement(item=item, movement_type="ENTRADA", quantity=Decimal(stock), user=resp_stock,
                                  reason="stock inicial de demonstração")
        artigos = {i.name: i for i in Item.objects.filter(restaurant=esquina)}
        for fornecedor, nome, ref, preco in [
            (frescos, "Tomate chucha", "", "1.20"),
            (frescos, "Alface frisada", "", "0.90"),
            (frescos, "Cebola", "", "0.65"),
            (mercearia, "Azeite virgem extra", "AZ-5L", "6.40"),
            (mercearia, "Guardanapos 33x33", "GD-33", "2.15"),
            (drogaria, "Lixívia alimentar", "LX-1", "1.10"),
        ]:
            if not fornecedor.items.filter(item=artigos[nome]).exists():
                save_supplier_item(supplier=fornecedor, item=artigos[nome], supplier_ref=ref,
                                   last_price=Decimal(preco), preferred=True)
        if not Receipt.objects.filter(restaurant=esquina).exists():
            receive(
                restaurant=esquina, supplier=frescos, user=resp_stock, document_number="GR 2026/311",
                document_date=timezone.localdate() - datetime.timedelta(days=7),
                lines=[(artigos["Tomate chucha"], Decimal(5), Decimal("1.15"), None)],
            )

    def _consumos(self, esquina, gerente, trabalhadores):
        """Fase 12: café e água com custo, uma refeição por turno, e os
        consumos de ontem da Marta, do Rui e uma oferta da casa."""
        from inventory.consumption import register_consumption
        from inventory.models import ConsumptionSettings, InternalConsumption

        regras = ConsumptionSettings.for_restaurant(esquina)
        if regras.meals_per_shift is None:
            regras.meals_per_shift = 1
            regras.save()
        bebidas = Category.objects.get(restaurant=esquina, name="Bebidas")
        artigos = {}
        for nome, custo, stock in [("Café (dose)", "0.18", "200"), ("Água 0,5 l", "0.25", "48")]:
            item, novo = Item.objects.get_or_create(
                restaurant=esquina, name=nome,
                defaults={"category": bebidas, "unit": Item.Unit.UN, "minimum_stock": Decimal(24), "reference_cost": Decimal(custo)},
            )
            if novo:
                register_movement(item=item, movement_type="ENTRADA", quantity=Decimal(stock), user=gerente,
                                  reason="stock inicial de demonstração")
            artigos[nome] = item
        if InternalConsumption.objects.filter(restaurant=esquina).exists():
            return
        ontem = timezone.localdate() - datetime.timedelta(days=1)
        for w in trabalhadores:
            register_consumption(
                restaurant=esquina, worker=w, reason=InternalConsumption.Reason.REFEICAO, day=ontem, user=gerente,
                lines=[(artigos["Café (dose)"], Decimal(1)), (artigos["Água 0,5 l"], Decimal(1))],
            )
        vinho = Item.objects.get(restaurant=esquina, name="Vinho tinto da casa")
        register_consumption(
            restaurant=esquina, worker=None, reason=InternalConsumption.Reason.OFERTA, day=ontem, user=gerente,
            lines=[(vinho, Decimal(1))], note="mesa 4, aniversário",
        )

    def _fichas(self, esquina, ribeira, gerente):
        """Fase 13: o Bitoque, com duas versões e um molho como preparação, e
        o café, ligados aos produtos do POS das duas casas. O Bacalhau à Brás
        e o resto ficam sem ficha, para a lista dos produtos do POS."""
        from recipes.models import Recipe
        from recipes.services import create_recipe, link_product, save_version
        from sales.models import PosProduct

        categorias = {c.name: c for c in Category.objects.filter(restaurant=esquina)}
        for nome, cat, unidade, custo, stock in [
            ("Bife da vazia", "Frescos", Item.Unit.KG, "12.00", "6"),
            ("Ovo", "Frescos", Item.Unit.UN, "0.20", "60"),
            ("Batata", "Frescos", Item.Unit.KG, "0.80", "20"),
            ("Arroz carolino", "Mercearia", Item.Unit.KG, "1.10", "10"),
        ]:
            item, novo = Item.objects.get_or_create(
                restaurant=esquina, name=nome,
                defaults={"category": categorias[cat], "unit": unidade, "minimum_stock": Decimal(1), "reference_cost": Decimal(custo)},
            )
            if novo:
                register_movement(item=item, movement_type="ENTRADA", quantity=Decimal(stock), user=gerente,
                                  reason="stock inicial de demonstração")
        # Os artigos que já existiam sem custo (o arroz que veio da Ribeira) ganham um.
        for nome, custo in (("Azeite virgem extra", "6.40"), ("Vinho tinto da casa", "2.50"), ("Arroz carolino", "1.10")):
            Item.objects.filter(restaurant=esquina, name=nome, reference_cost__isnull=True).update(reference_cost=Decimal(custo))
        grupo = esquina.organization
        if Recipe.objects.filter(organization=grupo).exists():
            return
        hoje = timezone.localdate()
        molho = create_recipe(
            organization=grupo, name="Molho do bitoque", kind=Recipe.Kind.PREPARACAO, user=gerente,
            portions=Decimal(10), valid_from=hoje - datetime.timedelta(days=60),
            notes="Alourar o alho no azeite, juntar o vinho e deixar reduzir a metade.",
            lines=[(("Azeite virgem extra", "L"), Decimal("0.2"), None), (("Vinho tinto da casa", "UN"), Decimal(1), None)],
        )
        linhas = [
            (("Bife da vazia", "KG"), Decimal("0.160"), None),
            (("Ovo", "UN"), Decimal(1), None),
            (("Batata", "KG"), Decimal("0.250"), Decimal(20)),
            (("Arroz carolino", "KG"), Decimal("0.100"), None),
            (molho, Decimal(1), None),
        ]
        bitoque = create_recipe(
            organization=grupo, name="Bitoque", kind=Recipe.Kind.PRATO, user=gerente, lines=linhas,
            valid_from=hoje - datetime.timedelta(days=60), notes="Bife na chapa, ovo estrelado por cima. Batata frita e arroz.",
        )
        linhas[0] = (("Bife da vazia", "KG"), Decimal("0.180"), None)
        save_version(recipe=bitoque, portions=1, lines=linhas, user=gerente, valid_from=hoje - datetime.timedelta(days=10),
                     notes="Bife na chapa, ovo estrelado por cima. Batata frita e arroz.")
        cafe = create_recipe(
            organization=grupo, name="Café", kind=Recipe.Kind.BEBIDA, user=gerente,
            lines=[(("Café (dose)", "UN"), Decimal(1), None)], valid_from=hoje - datetime.timedelta(days=60),
        )
        for casa in (esquina, ribeira):
            for ficha, codigo in ((bitoque, "P001"), (cafe, "C001")):
                produto = PosProduct.objects.filter(restaurant=casa, code=codigo).first()
                if produto is not None:
                    link_product(recipe=ficha, product=produto, user=gerente)
