from django.db import models


class TimeStampedModel(models.Model):
    """Base abstrata de todos os modelos operacionais."""

    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        abstract = True


class Restaurant(TimeStampedModel):
    """
    Multi-tenant preparado, não exposto: o MVP serve um restaurante por
    instância, mas todos os modelos operacionais apontam para aqui desde
    a primeira migração (secção 2 do plano).
    """

    name = models.CharField("nome", max_length=120)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "restaurante"

    def __str__(self):
        return self.name


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
