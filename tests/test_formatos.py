"""Tarefa D1: as quantidades escrevem-se da mesma maneira em todo o lado
(4 kg, 0,22 L), com a unidade em minúsculas."""
import re
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from core.formatos import quantidade
from inventory.models import Category, Item, StockMovement
from inventory.services import register_movement


@pytest.mark.parametrize("valor,unidade,texto", [
    ("4.000", "KG", "4 kg"), ("0.220", "L", "0,22 L"), ("1.125", "KG", "1,125 kg"),
    ("-6", "UN", "-6 un"), ("1250.5", "KG", "1 250,5 kg"), (None, "UN", "—"),
    ("20.000", "UN", "20 un"),  # normalize() dá 2E+1: expoente positivo
    ("1.0004", "KG", "1 kg"), ("1.1265", "KG", "1,127 kg"), ("-0.0004", "KG", "0 kg"),  # arredonda às 3 casas
])
def test_quantidade(valor, unidade, texto):
    assert quantidade(Decimal(valor) if valor else None, unidade) == texto


def test_quantidade_aceita_float_e_texto_vazio():
    assert quantidade(0.22, "L") == "0,22 L"
    assert quantidade("", "UN") == "—"


def test_templates_nao_mostram_stock_nem_unidades_em_bruto():
    # As fichas técnicas ficam de fora: as linhas guardam a unidade em texto
    # livre (minor adiado da D1).
    padrao = re.compile(r"\{\{\s*[\w.]*(current_stock|minimum_stock|\.unit|\.unidade)\s*\}\}")
    sujos = [
        p for p in Path("templates").rglob("*.html")
        if "recipes" not in p.parts and padrao.search(p.read_text(encoding="utf-8"))
    ]
    assert sujos == []


ECRAS_DE_STOCK = [
    "templates/manage/inventory", "templates/partials/inventory", "templates/manage/purchasing",
    "templates/manage/analytics/stock.html", "templates/manage/analytics/compras.html", "templates/manage/dashboard.html",
]


def test_ecras_de_stock_so_usam_numero_nas_percentagens():
    """`numero` arredonda às 2 casas (1,125 → 1,12) e `numero:3` deixa zeros
    (1,500): as quantidades de stock escrevem-se com `quantidade`."""
    padrao = re.compile(r"\{\{\s*([\w.]+)\s*\|\s*numero")
    caminhos = [p for c in map(Path, ECRAS_DE_STOCK) for p in (sorted(c.rglob("*.html")) if c.is_dir() else [c])]
    sujos = [
        f"{p.as_posix()}: {campo}"
        for p in caminhos for campo in padrao.findall(p.read_text(encoding="utf-8"))
        if not campo.endswith("_pct")
    ]
    assert sujos == []


def _mercearia(restaurant):
    # Cada casa nova já nasce com a categoria «Mercearia» (inventory/signals.py).
    return Category.objects.get_or_create(restaurant=restaurant, name="Mercearia")[0]


def test_mensagem_de_stock_negativo_formatada(restaurant, stock_user):
    item = Item.objects.create(restaurant=restaurant, name="Arroz", unit="KG", category=_mercearia(restaurant))
    with pytest.raises(ValidationError, match="-2 kg"):
        register_movement(item=item, movement_type=StockMovement.Type.SAIDA, quantity=2, user=stock_user)


def test_lista_de_stock_mostra_a_quantidade_formatada(client, restaurant, stock_user):
    item = Item.objects.create(restaurant=restaurant, name="Arroz", unit="KG", category=_mercearia(restaurant))
    register_movement(item=item, movement_type=StockMovement.Type.ENTRADA, quantity=Decimal("4.000"), user=stock_user)
    client.force_login(stock_user)
    html = client.get(reverse("inventory:lista")).content.decode()
    assert ">4 kg<" in html


def test_encomenda_parcial_escreve_as_quantidades_da_mesma_maneira(client, restaurant, stock_user):
    """Na linha da encomenda, o encomendado, o recebido e o que falta (antes:
    «3,75 kg | 2,50 | 1,25», três formatos numa linha)."""
    from purchasing import services as compras
    from purchasing.models import Supplier

    arroz = Item.objects.create(restaurant=restaurant, name="Arroz", unit="KG", category=_mercearia(restaurant))
    fornecedor = Supplier.objects.create(organization=restaurant.organization, name="Mercearia Central")
    encomenda = compras.create_order(
        restaurant=restaurant, supplier=fornecedor, lines=[(arroz, Decimal("3.75"), Decimal("1.10"))], user=stock_user
    )
    compras.send_order(order=encomenda, user=stock_user)
    compras.receive(
        restaurant=restaurant, supplier=fornecedor, user=stock_user, order=encomenda,
        lines=[(arroz, Decimal("2.5"), Decimal("1.10"), encomenda.lines.get())],
        document_number="GR 1", document_date=timezone.localdate(),
    )
    client.force_login(stock_user)
    html = client.get(reverse("purchasing:encomenda", args=[encomenda.pk])).content.decode()
    assert ">3,75 kg<" in html and ">2,5 kg<" in html and ">1,25 kg<" in html


def test_core_nao_depende_de_sales_para_formatar():
    """Os gráficos do core usam os formatos do core, não os filtros das vendas."""
    texto = Path("core/templatetags/graficos.py").read_text(encoding="utf-8")
    assert "sales.templatetags" not in texto
