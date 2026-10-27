import core.validators
from django.db import migrations, models
from django.utils.text import slugify

RESERVADOS = {"app", "www", "admin", "api", "static", "media", "mail", "email", "ftp", "suporte"}


def preencher(apps, schema_editor):
    """Cada grupo que já existe fica com um endereço tirado do nome."""
    Organization = apps.get_model("core", "Organization")
    usados = set()
    for grupo in Organization.objects.order_by("pk"):
        base = slugify(grupo.name).replace("_", "-")[:30].strip("-") or "grupo"
        if base in RESERVADOS:
            base = f"{base}-grupo"
        candidato, n = base, 2
        while candidato in usados:
            candidato, n = f"{base}-{n}", n + 1
        usados.add(candidato)
        grupo.subdomain = candidato
        grupo.save(update_fields=["subdomain"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_grupo_e_casas"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="subdomain",
            field=models.CharField(max_length=40, null=True, verbose_name="endereço"),
        ),
        migrations.RunPython(preencher, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="organization",
            name="subdomain",
            field=models.CharField(
                help_text="O grupo entra em <endereço>.opero.pt. Letras minúsculas, números e hífenes. "
                "Mudá-lo obriga a ativar de novo os tablets e a instalar de novo a app.",
                max_length=40,
                unique=True,
                validators=[core.validators.validate_subdomain],
                verbose_name="endereço",
            ),
        ),
    ]
