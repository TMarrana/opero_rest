"""
Fornecedores e compras (Fase 11).

Os fornecedores são do grupo; os artigos, as encomendas e as receções são
de cada casa. Uma receção dá entrada no stock só através do
`register_movement()` (invariante 1), com a origem «compra», e nunca se
apaga (invariante 2): um erro corrige-se com um ajuste.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel
from core.validators import validate_nif

DIAS_SEMANA = [("0", "Seg"), ("1", "Ter"), ("2", "Qua"), ("3", "Qui"), ("4", "Sex"), ("5", "Sáb"), ("6", "Dom")]


class Supplier(TimeStampedModel):
    """Um fornecedor do grupo. Com encomendas ou receções, arquiva-se em vez
    de se apagar."""

    organization = models.ForeignKey(
        "core.Organization", verbose_name="grupo", on_delete=models.CASCADE, related_name="suppliers"
    )
    name = models.CharField("nome", max_length=120)
    nif = models.CharField("NIF", max_length=9, blank=True, validators=[validate_nif])
    contact_name = models.CharField("pessoa de contacto", max_length=120, blank=True)
    phone = models.CharField("telefone", max_length=40, blank=True)
    email = models.EmailField("email", blank=True)
    # Dias da semana em que entrega, como «0,3» (segunda e quinta).
    delivery_days = models.CharField("dias de entrega", max_length=20, blank=True)
    notes = models.TextField("observações", blank=True)
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "fornecedor"
        verbose_name_plural = "fornecedores"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "name"], name="fornecedor_unico_por_grupo"),
        ]

    def __str__(self):
        return self.name

    def delivery_days_display(self):
        nomes = dict(DIAS_SEMANA)
        return ", ".join(nomes[d] for d in self.delivery_days.split(",") if d in nomes)

    def has_history(self):
        return self.orders.exists() or self.receipts.exists()


class SupplierItem(TimeStampedModel):
    """Um artigo de uma casa que este fornecedor vende. A unidade de compra
    é a do artigo, porque a conversão de unidades está fora (docx)."""

    supplier = models.ForeignKey(Supplier, verbose_name="fornecedor", on_delete=models.CASCADE, related_name="items")
    item = models.ForeignKey(
        "inventory.Item", verbose_name="artigo", on_delete=models.CASCADE, related_name="supplier_items"
    )
    supplier_ref = models.CharField("referência do fornecedor", max_length=60, blank=True)
    last_price = models.DecimalField("último preço", max_digits=12, decimal_places=4, null=True, blank=True)
    last_price_at = models.DateField("último preço em", null=True, blank=True)
    preferred = models.BooleanField("fornecedor preferido", default=False)

    class Meta:
        verbose_name = "artigo do fornecedor"
        verbose_name_plural = "artigos do fornecedor"
        ordering = ["item__name"]
        constraints = [
            models.UniqueConstraint(fields=["supplier", "item"], name="artigo_fornecedor_unico"),
            models.UniqueConstraint(
                fields=["item"], condition=Q(preferred=True), name="um_fornecedor_preferido_por_artigo"
            ),
        ]

    def __str__(self):
        return f"{self.item} · {self.supplier}"


class PurchaseOrder(TimeStampedModel):
    class State(models.TextChoices):
        RASCUNHO = "RASCUNHO", "Rascunho"
        ENVIADA = "ENVIADA", "Enviada"
        PARCIAL = "PARCIAL", "Recebida em parte"
        RECEBIDA = "RECEBIDA", "Recebida"
        CANCELADA = "CANCELADA", "Cancelada"

    OPEN_STATES = (State.RASCUNHO, State.ENVIADA, State.PARCIAL)

    restaurant = models.ForeignKey(
        "core.Restaurant", verbose_name="restaurante", on_delete=models.CASCADE, related_name="purchase_orders"
    )
    supplier = models.ForeignKey(Supplier, verbose_name="fornecedor", on_delete=models.PROTECT, related_name="orders")
    state = models.CharField("estado", max_length=10, choices=State.choices, default=State.RASCUNHO)
    expected_date = models.DateField("entrega prevista", null=True, blank=True)
    notes = models.CharField("observações para o fornecedor", max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="criada por", on_delete=models.PROTECT, related_name="+"
    )
    sent_at = models.DateTimeField("enviada em", null=True, blank=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="enviada por", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    cancelled_at = models.DateTimeField("cancelada em", null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="cancelada por", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "encomenda"
        verbose_name_plural = "encomendas"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.reference

    @property
    def reference(self):
        return f"ENC-{self.pk}"

    @property
    def is_open(self):
        return self.state in self.OPEN_STATES

    def total(self):
        return sum((l.total() or Decimal(0) for l in self.lines.all()), Decimal(0))


class PurchaseOrderLine(models.Model):
    order = models.ForeignKey(PurchaseOrder, verbose_name="encomenda", on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey("inventory.Item", verbose_name="artigo", on_delete=models.PROTECT, related_name="+")
    quantity = models.DecimalField("quantidade", max_digits=12, decimal_places=3)
    unit_price = models.DecimalField("preço previsto", max_digits=12, decimal_places=4, null=True, blank=True)

    class Meta:
        verbose_name = "linha de encomenda"
        verbose_name_plural = "linhas de encomenda"
        ordering = ["item__name"]
        constraints = [
            models.UniqueConstraint(fields=["order", "item"], name="artigo_unico_por_encomenda"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="encomenda_quantidade_positiva"),
        ]

    def __str__(self):
        return f"{self.order} · {self.item}"

    def total(self):
        return None if self.unit_price is None else (self.quantity * self.unit_price).quantize(Decimal("0.01"))

    def received(self):
        return self.receipt_lines.aggregate(t=models.Sum("quantity"))["t"] or Decimal(0)

    def pending(self):
        return max(self.quantity - self.received(), Decimal(0))


class Receipt(TimeStampedModel):
    """Uma receção de mercadoria, com ou sem encomenda. Não se apaga."""

    restaurant = models.ForeignKey(
        "core.Restaurant", verbose_name="restaurante", on_delete=models.CASCADE, related_name="receipts"
    )
    supplier = models.ForeignKey(Supplier, verbose_name="fornecedor", on_delete=models.PROTECT, related_name="receipts")
    order = models.ForeignKey(
        PurchaseOrder, verbose_name="encomenda", on_delete=models.PROTECT, null=True, blank=True, related_name="receipts"
    )
    document_number = models.CharField("número da fatura ou guia", max_length=60)
    document_date = models.DateField("data da fatura ou guia")
    received_at = models.DateTimeField("recebida em")
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="recebida por", on_delete=models.PROTECT, related_name="+"
    )
    notes = models.CharField("observações", max_length=300, blank=True)

    class Meta:
        verbose_name = "receção"
        verbose_name_plural = "receções"
        ordering = ["-received_at", "-id"]

    def __str__(self):
        return self.reference

    @property
    def reference(self):
        return f"REC-{self.pk}"

    def total(self):
        return sum((l.total() or Decimal(0) for l in self.lines.all()), Decimal(0))


class ReceiptLine(models.Model):
    receipt = models.ForeignKey(Receipt, verbose_name="receção", on_delete=models.PROTECT, related_name="lines")
    item = models.ForeignKey("inventory.Item", verbose_name="artigo", on_delete=models.PROTECT, related_name="receipt_lines")
    order_line = models.ForeignKey(
        PurchaseOrderLine,
        verbose_name="linha da encomenda",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="receipt_lines",
    )
    quantity = models.DecimalField("quantidade", max_digits=12, decimal_places=3)
    unit_price = models.DecimalField("preço unitário", max_digits=12, decimal_places=4, null=True, blank=True)
    movement = models.OneToOneField(
        "inventory.StockMovement", verbose_name="movimento", on_delete=models.PROTECT, related_name="receipt_line"
    )

    class Meta:
        verbose_name = "linha de receção"
        verbose_name_plural = "linhas de receção"
        ordering = ["item__name"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="rececao_quantidade_positiva"),
        ]

    def __str__(self):
        return f"{self.receipt} · {self.item}"

    def total(self):
        return None if self.unit_price is None else (self.quantity * self.unit_price).quantize(Decimal("0.01"))
