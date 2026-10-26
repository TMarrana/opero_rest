from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class Category(TimeStampedModel):
    restaurant = models.ForeignKey(
        "core.Restaurant", verbose_name="restaurante", on_delete=models.CASCADE, related_name="categories"
    )
    name = models.CharField("nome", max_length=80)

    class Meta:
        verbose_name = "categoria"
        constraints = [
            models.UniqueConstraint(fields=["restaurant", "name"], name="categoria_unica_por_restaurante"),
        ]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Item(TimeStampedModel):
    class Unit(models.TextChoices):
        UN = "UN", "unidade"
        KG = "KG", "quilograma"
        L = "L", "litro"
        CX = "CX", "caixa"
        EMB = "EMB", "embalagem"

    restaurant = models.ForeignKey(
        "core.Restaurant", verbose_name="restaurante", on_delete=models.CASCADE, related_name="items"
    )
    name = models.CharField("nome", max_length=120)
    category = models.ForeignKey(
        Category, verbose_name="categoria", on_delete=models.PROTECT, related_name="items"
    )
    unit = models.CharField("unidade", max_length=3, choices=Unit.choices, default=Unit.UN)
    # Invariante 1: só register_movement() escreve este campo. Nenhuma
    # view nem form o expõe; no admin é read-only.
    current_stock = models.DecimalField("stock atual", max_digits=12, decimal_places=3, default=0)
    minimum_stock = models.DecimalField("stock mínimo", max_digits=12, decimal_places=3, default=0)
    reference_cost = models.DecimalField(
        "custo de referência", max_digits=10, decimal_places=2, null=True, blank=True
    )
    is_active = models.BooleanField("ativo", default=True)
    notes = models.TextField("notas", blank=True)

    class Meta:
        verbose_name = "artigo"
        constraints = [
            models.UniqueConstraint(fields=["restaurant", "name"], name="artigo_unico_por_restaurante"),
        ]
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def is_low(self):
        return self.current_stock <= self.minimum_stock


class StockTransfer(TimeStampedModel):
    """Transferência de stock entre duas casas do mesmo grupo (Fase 9): uma
    saída numa casa e uma entrada na outra, criadas juntas por
    inventory/services.py::transfer_stock() e ligadas a esta linha."""

    source_item = models.ForeignKey(
        Item, verbose_name="artigo de origem", on_delete=models.PROTECT, related_name="transfers_out"
    )
    destination_item = models.ForeignKey(
        Item, verbose_name="artigo de destino", on_delete=models.PROTECT, related_name="transfers_in"
    )
    quantity = models.DecimalField("quantidade", max_digits=12, decimal_places=3)
    occurred_at = models.DateTimeField("ocorreu em")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="registado por", on_delete=models.PROTECT, related_name="stock_transfers"
    )
    note = models.CharField("observação", max_length=200, blank=True)

    class Meta:
        verbose_name = "transferência de stock"
        verbose_name_plural = "transferências de stock"
        ordering = ["-occurred_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="transferencia_quantidade_positiva"),
        ]

    def __str__(self):
        return f"{self.source_item.restaurant} → {self.destination_item.restaurant}: {self.quantity} {self.source_item}"


class StockMovement(TimeStampedModel):
    """
    Imutável e sem delete (invariante 2): correções fazem-se com novos
    movimentos de ajuste. Criado exclusivamente por
    inventory/services.py::register_movement().
    """

    class Type(models.TextChoices):
        ENTRADA = "ENTRADA", "Entrada"
        SAIDA = "SAIDA", "Saída"
        AJUSTE_POS = "AJUSTE_POS", "Ajuste +"
        AJUSTE_NEG = "AJUSTE_NEG", "Ajuste −"

    class Origin(models.TextChoices):
        """De onde vem o movimento (Fase 9), para os relatórios separarem uma
        quebra de uma venda. A Fase 11 junta a compra; as seguintes, o
        consumo interno e a venda."""

        MANUAL = "MANUAL", "Registo manual"
        TRANSFERENCIA = "TRANSFERENCIA", "Transferência entre casas"
        COMPRA = "COMPRA", "Compra"

    item = models.ForeignKey(Item, verbose_name="artigo", on_delete=models.PROTECT, related_name="movements")
    movement_type = models.CharField("tipo", max_length=10, choices=Type.choices)
    quantity = models.DecimalField("quantidade", max_digits=12, decimal_places=3)
    occurred_at = models.DateTimeField("ocorreu em")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="registado por", on_delete=models.PROTECT, related_name="stock_movements"
    )
    reason = models.CharField("motivo", max_length=200, blank=True)
    reference = models.CharField("referência", max_length=80, blank=True)
    origin = models.CharField("origem", max_length=20, choices=Origin.choices, default=Origin.MANUAL)
    transfer = models.ForeignKey(
        StockTransfer,
        verbose_name="transferência",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movements",
    )

    class Meta:
        verbose_name = "movimento de stock"
        verbose_name_plural = "movimentos de stock"
        ordering = ["-occurred_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="movimento_quantidade_positiva"),
        ]

    def __str__(self):
        return f"{self.get_movement_type_display()} - {self.item} - {self.quantity}"

    @property
    def signed_quantity(self):
        if self.movement_type in (self.Type.SAIDA, self.Type.AJUSTE_NEG):
            return -self.quantity
        return self.quantity
