"""
Fichas técnicas (Fase 13).

As fichas são do grupo; os artigos continuam a ser de cada casa (decisão da
secção 12 por tomar). Por isso uma linha guarda o nome e a unidade do artigo,
e em cada casa liga-se ao artigo com o mesmo nome e a mesma unidade. O custo
é o de cada casa, com o `reference_cost` dos artigos de lá.

Mudar a receita cria uma versão nova, com a data a partir da qual vale. O
consumo de um dia passado calcula-se com a versão em vigor nesse dia (Fase 14).
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel


class Recipe(TimeStampedModel):
    class Kind(models.TextChoices):
        PRATO = "PRATO", "Prato"
        BEBIDA = "BEBIDA", "Bebida"
        PREPARACAO = "PREPARACAO", "Preparação"

    organization = models.ForeignKey(
        "core.Organization", verbose_name="grupo", on_delete=models.CASCADE, related_name="recipes"
    )
    name = models.CharField("nome", max_length=120)
    kind = models.CharField("tipo", max_length=10, choices=Kind.choices, default=Kind.PRATO)
    sale_price = models.DecimalField(
        "preço de venda de referência, sem IVA",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Só conta quando a ficha não está ligada a um produto do POS com preço.",
    )
    is_active = models.BooleanField("ativa", default=True)

    class Meta:
        verbose_name = "ficha técnica"
        verbose_name_plural = "fichas técnicas"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "name"], name="ficha_unica_por_grupo"),
        ]

    def __str__(self):
        return self.name

    def current_version(self):
        """A versão em vigor hoje, ou a primeira se todas começam depois."""
        from django.utils import timezone

        return self.version_on(timezone.localdate()) or self.versions.order_by("valid_from", "number").first()

    def version_on(self, day):
        """A versão em vigor num dia: a mais recente que já tinha começado.
        Duas no mesmo dia: vale a última criada."""
        return self.versions.filter(valid_from__lte=day).order_by("-valid_from", "-number").first()


class RecipeVersion(models.Model):
    """Uma versão da receita. Não se muda depois de criada: uma alteração é
    uma versão nova."""

    recipe = models.ForeignKey(Recipe, verbose_name="ficha", on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField("versão")
    valid_from = models.DateField("em vigor a partir de")
    # As quantidades das linhas são as da receita inteira, que dá estas doses.
    portions = models.DecimalField("doses", max_digits=8, decimal_places=2, default=1)
    notes = models.TextField("preparação", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="criada por", on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField("criada em", auto_now_add=True)

    class Meta:
        verbose_name = "versão da ficha"
        verbose_name_plural = "versões da ficha"
        ordering = ["recipe", "-number"]
        constraints = [
            models.UniqueConstraint(fields=["recipe", "number"], name="versao_unica_por_ficha"),
            models.CheckConstraint(condition=Q(portions__gt=0), name="ficha_doses_positivas"),
        ]

    def __str__(self):
        return f"{self.recipe} · v{self.number}"


class RecipeLine(models.Model):
    """Um artigo (pelo nome e unidade) ou uma preparação, com a quantidade
    limpa e a quebra. A quantidade bruta, que sai do stock, é a limpa a
    dividir por (1 − quebra)."""

    version = models.ForeignKey(RecipeVersion, verbose_name="versão", on_delete=models.CASCADE, related_name="lines")
    item_name = models.CharField("artigo", max_length=120, blank=True)
    unit = models.CharField("unidade", max_length=3, blank=True)
    preparation = models.ForeignKey(
        Recipe,
        verbose_name="preparação",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="used_in_lines",
    )
    # Numa preparação, a quantidade é em doses dessa preparação.
    quantity = models.DecimalField("quantidade", max_digits=12, decimal_places=3)
    waste_pct = models.DecimalField("quebra (%)", max_digits=5, decimal_places=2, default=0)

    class Meta:
        verbose_name = "linha da ficha"
        verbose_name_plural = "linhas da ficha"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="ficha_quantidade_positiva"),
            models.CheckConstraint(condition=Q(waste_pct__gte=0, waste_pct__lt=100), name="ficha_quebra_valida"),
            models.CheckConstraint(
                condition=(Q(preparation__isnull=True) & ~Q(item_name=""))
                | (Q(preparation__isnull=False) & Q(item_name="")),
                name="ficha_linha_artigo_ou_preparacao",
            ),
        ]

    def __str__(self):
        return f"{self.version} · {self.label}"

    @property
    def label(self):
        return self.preparation.name if self.preparation_id else self.item_name

    @property
    def unit_label(self):
        return "dose" if self.preparation_id else self.unit


class RecipeProduct(models.Model):
    """A ligação de uma ficha a um produto do POS de uma casa. O mesmo prato
    pode ter códigos diferentes em cada casa ou em cada menu; um produto do
    POS tem no máximo uma ficha."""

    recipe = models.ForeignKey(Recipe, verbose_name="ficha", on_delete=models.CASCADE, related_name="products")
    product = models.OneToOneField(
        "sales.PosProduct", verbose_name="produto do POS", on_delete=models.CASCADE, related_name="recipe_link"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="ligado por", on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField("ligado em", auto_now_add=True)

    class Meta:
        verbose_name = "produto do POS da ficha"
        verbose_name_plural = "produtos do POS da ficha"
        ordering = ["product__description"]

    def __str__(self):
        return f"{self.recipe} · {self.product.code}"
