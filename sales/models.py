"""
Vendas lidas do ficheiro SAF-T (PT) de faturação que o POS exporta (Fase 10).

Só leitura: nada aqui mexe no stock (isso é a Fase 14) nem emite documentos.
Do cliente final não se guarda nada, e o ficheiro original também não: fica
só o hash, para reconhecer um ficheiro repetido.
"""
from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class SalesSettings(TimeStampedModel):
    """Regras de vendas de uma casa. Criadas quando são precisas, com os
    valores por omissão (`for_restaurant`)."""

    restaurant = models.OneToOneField(
        "core.Restaurant", verbose_name="restaurante", on_delete=models.CASCADE, related_name="sales_settings"
    )
    # Proposta da secção 12: 5h. Um jantar que fecha à 1h conta no dia em que começou.
    day_cutoff_hour = models.PositiveSmallIntegerField(
        "hora de corte do dia de serviço",
        default=5,
        help_text="As vendas antes desta hora contam no dia anterior. Entre 0 e 11.",
    )
    series = models.CharField(
        "séries desta casa",
        max_length=200,
        blank=True,
        help_text="Só é preciso quando várias casas faturam com o mesmo NIF. "
        "As séries dos documentos desta casa, separadas por vírgulas, como aparecem no número: "
        "em «FS 2026A/123», a série é 2026A.",
    )
    hourly_cost = models.DecimalField(
        "custo médio por hora de trabalho",
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Opcional. Dá o custo de pessoal estimado em percentagem das vendas. Sem salários: é uma média.",
    )

    class Meta:
        verbose_name = "regras de vendas"
        verbose_name_plural = "regras de vendas"

    def __str__(self):
        return f"Vendas · {self.restaurant}"

    @classmethod
    def for_restaurant(cls, restaurant):
        return cls.objects.get_or_create(restaurant=restaurant)[0]

    def series_list(self):
        return [s.strip() for s in self.series.split(",") if s.strip()]


class SalesImport(TimeStampedModel):
    """Uma importação de um ficheiro SAF-T numa casa."""

    restaurant = models.ForeignKey(
        "core.Restaurant", verbose_name="restaurante", on_delete=models.CASCADE, related_name="sales_imports"
    )
    file_name = models.CharField("ficheiro", max_length=200)
    file_hash = models.CharField("hash do ficheiro", max_length=64, db_index=True)
    period_start = models.DateField("início do período")
    period_end = models.DateField("fim do período")
    tax_id = models.CharField("NIF do ficheiro", max_length=20)
    product_id = models.CharField("programa", max_length=255, blank=True)
    certificate_number = models.CharField("certificado do programa", max_length=20, blank=True)
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="importado por", on_delete=models.PROTECT, related_name="+"
    )
    documents_new = models.PositiveIntegerField("documentos novos", default=0)
    documents_updated = models.PositiveIntegerField("documentos com estado alterado", default=0)
    documents_unchanged = models.PositiveIntegerField("documentos já importados", default=0)
    documents_other_series = models.PositiveIntegerField("documentos de outras séries", default=0)
    other_series = models.CharField("outras séries no ficheiro", max_length=200, blank=True)
    # Os totais de controlo de SalesInvoices não batem com as linhas lidas.
    control_mismatch = models.BooleanField("totais de controlo diferentes", default=False)

    class Meta:
        verbose_name = "importação SAF-T"
        verbose_name_plural = "importações SAF-T"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.restaurant} · {self.period_start:%d/%m/%Y} a {self.period_end:%d/%m/%Y}"


class PosProduct(TimeStampedModel):
    """Um produto do POS, numa casa. Vem de `MasterFiles/Product`; a Fase 13
    liga-o às fichas técnicas."""

    restaurant = models.ForeignKey(
        "core.Restaurant", verbose_name="restaurante", on_delete=models.CASCADE, related_name="pos_products"
    )
    code = models.CharField("código no POS", max_length=60)
    description = models.CharField("descrição", max_length=200)
    group = models.CharField("família", max_length=100, blank=True)
    last_price = models.DecimalField("último preço sem IVA", max_digits=12, decimal_places=4, null=True, blank=True)
    last_price_at = models.DateTimeField("último preço em", null=True, blank=True)

    class Meta:
        verbose_name = "produto do POS"
        verbose_name_plural = "produtos do POS"
        ordering = ["description"]
        constraints = [
            models.UniqueConstraint(fields=["restaurant", "code"], name="produto_pos_unico_por_casa"),
        ]

    def __str__(self):
        return self.description


class SalesDocumentQuerySet(models.QuerySet):
    def valid(self):
        """Os documentos que contam: sem os anulados (A) e sem os já
        faturados noutro documento (F), que contariam duas vezes."""
        return self.exclude(status__in=SalesDocument.EXCLUDED_STATUSES)


class SalesDocument(TimeStampedModel):
    """Um documento de `SalesInvoices`. Os valores são guardados com sinal:
    uma nota de crédito tem totais negativos e abate às vendas."""

    class Type(models.TextChoices):
        FT = "FT", "Fatura"
        FS = "FS", "Fatura simplificada"
        FR = "FR", "Fatura-recibo"
        NC = "NC", "Nota de crédito"
        ND = "ND", "Nota de débito"

    EXCLUDED_STATUSES = ("A", "F")
    SALE_TYPES = (Type.FT, Type.FS, Type.FR)

    restaurant = models.ForeignKey(
        "core.Restaurant", verbose_name="restaurante", on_delete=models.CASCADE, related_name="sales_documents"
    )
    sales_import = models.ForeignKey(
        SalesImport, verbose_name="importação", on_delete=models.PROTECT, related_name="documents"
    )
    number = models.CharField("número", max_length=60)
    doc_type = models.CharField("tipo", max_length=2, choices=Type.choices)
    series = models.CharField("série", max_length=60, blank=True)
    status = models.CharField("estado", max_length=1)
    invoice_date = models.DateField("data do documento")
    system_entry = models.DateTimeField("hora da venda")
    service_date = models.DateField("dia de serviço", db_index=True)
    net_total = models.DecimalField("total sem IVA", max_digits=14, decimal_places=2)
    gross_total = models.DecimalField("total com IVA", max_digits=14, decimal_places=2)
    # O operador do POS. Não se liga ao trabalhador até haver decisão (secção 12).
    source_id = models.CharField("operador no POS", max_length=60, blank=True)

    objects = SalesDocumentQuerySet.as_manager()

    class Meta:
        verbose_name = "documento de venda"
        verbose_name_plural = "documentos de venda"
        ordering = ["system_entry"]
        constraints = [
            models.UniqueConstraint(fields=["restaurant", "number"], name="documento_venda_unico_por_casa"),
        ]
        indexes = [models.Index(fields=["restaurant", "service_date"])]

    def __str__(self):
        return self.number


class SalesLine(models.Model):
    """Uma linha de um documento. Quantidade e valor têm o sinal do
    documento: numa nota de crédito são negativos."""

    document = models.ForeignKey(SalesDocument, verbose_name="documento", on_delete=models.CASCADE, related_name="lines")
    line_number = models.PositiveIntegerField("linha")
    product = models.ForeignKey(PosProduct, verbose_name="produto", on_delete=models.PROTECT, related_name="lines")
    description = models.CharField("descrição", max_length=200)
    quantity = models.DecimalField("quantidade", max_digits=14, decimal_places=3)
    unit = models.CharField("unidade", max_length=20, blank=True)
    unit_price = models.DecimalField("preço unitário sem IVA", max_digits=14, decimal_places=4)
    net_amount = models.DecimalField("valor sem IVA", max_digits=14, decimal_places=2)
    tax_rate = models.DecimalField("taxa de IVA", max_digits=5, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = "linha de venda"
        verbose_name_plural = "linhas de venda"
        ordering = ["document", "line_number"]

    def __str__(self):
        return f"{self.document} · {self.line_number}"
