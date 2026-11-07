"""Tarefa D1: as quantidades escrevem-se da mesma maneira em todo o lado
(4 kg, 0,22 L), com a unidade em minúsculas."""
import re
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from core.formatos import quantidade
from inventory.models import Category, Item, StockMovement
from inventory.services import register_movement


@pytest.mark.parametrize("valor,unidade,texto", [
    ("4.000", "KG", "4 kg"), ("0.220", "L", "0,22 L"), ("1.125", "KG", "1,125 kg"),
    ("-6", "UN", "-6 un"), ("1250.5", "KG", "1 250,5 kg"), (None, "UN", "—"),
    ("20.000", "UN", "20 un"),  # normalize() dá 2E+1: expoente positivo
])
def test_quantidade(valor, unidade, texto):
    assert quantidade(Decimal(valor) if valor else None, unidade) == texto


def test_templates_nao_mostram_stock_nem_unidades_em_bruto():
    padrao = re.compile(r"\{\{\s*[\w.]*(current_stock|minimum_stock|\.unit)\s*\}\}")
    sujos = [p for p in Path("templates").rglob("*.html") if padrao.search(p.read_text(encoding="utf-8"))]
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
