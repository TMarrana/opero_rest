from django.db import models

from .validators import validate_nif


class TimeStampedModel(models.Model):
    """Base abstrata de todos os modelos operacionais."""

    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        abstract = True


class Organization(TimeStampedModel):
    """O cliente, que no ecrã se chama «Grupo» (Fase 9): junta as casas que
    gere na mesma conta. O Admin do grupo vê e configura todas."""

    name = models.CharField("nome", max_length=120)
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "grupo"

    def __str__(self):
        return self.name


class Restaurant(TimeStampedModel):
    """
    Uma casa do grupo. Todos os modelos operacionais apontam para aqui
    desde a primeira migração (secção 2 do plano); desde a Fase 9 o
    mesmo cliente pode ter várias, e cada pedido do backoffice trabalha
    numa só (`core.middleware.ActiveRestaurantMiddleware`).
    """

    organization = models.ForeignKey(
        Organization, verbose_name="grupo", on_delete=models.PROTECT, related_name="restaurants"
    )
    name = models.CharField("nome", max_length=120)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField("ativo", default=True)
    nif = models.CharField("NIF", max_length=9, blank=True, validators=[validate_nif])
    address = models.CharField("morada", max_length=200, blank=True)
    municipality = models.CharField(
        "concelho", max_length=80, blank=True, help_text="Para saber que feriado municipal se aplica."
    )

    class Meta:
        verbose_name = "restaurante"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Uma casa criada sem grupo é um cliente novo com uma só casa.
        if self.organization_id is None:
            self.organization = Organization.objects.create(name=self.name)
        super().save(*args, **kwargs)


class WorkArea(TimeStampedModel):
    """Área de trabalho: cozinha, sala, bar (Fase 5). O dispositivo do
    restaurante fica associado a uma área, e cada marcação herda a área
    do dispositivo onde foi feita. Arquiva-se em vez de se apagar, porque
    as marcações já feitas apontam para ela."""

    restaurant = models.ForeignKey(
        Restaurant, verbose_name="restaurante", on_delete=models.CASCADE, related_name="work_areas"
    )
    name = models.CharField("nome", max_length=60)
    archived_at = models.DateTimeField("arquivada em", null=True, blank=True)

    class Meta:
        verbose_name = "área de trabalho"
        verbose_name_plural = "áreas de trabalho"
        ordering = ["name"]

    def __str__(self):
        return self.name
