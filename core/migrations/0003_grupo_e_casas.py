"""Fase 9: o grupo (cliente) e os dados da casa. Cada restaurante que já
existe fica sozinho num grupo com o mesmo nome."""
import django.db.models.deletion
from django.db import migrations, models

import core.validators


def criar_grupos(apps, schema_editor):
    Organization = apps.get_model("core", "Organization")
    Restaurant = apps.get_model("core", "Restaurant")
    for restaurant in Restaurant.objects.filter(organization__isnull=True):
        restaurant.organization = Organization.objects.create(name=restaurant.name)
        restaurant.save(update_fields=["organization"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_fase5"),
    ]

    operations = [
        migrations.CreateModel(
            name="Organization",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                ("name", models.CharField(max_length=120, verbose_name="nome")),
                ("is_active", models.BooleanField(default=True, verbose_name="ativo")),
            ],
            options={"verbose_name": "grupo"},
        ),
        migrations.AlterModelOptions(
            name="restaurant",
            options={"ordering": ["name"], "verbose_name": "restaurante"},
        ),
        migrations.AddField(
            model_name="restaurant",
            name="organization",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="restaurants",
                to="core.organization",
                verbose_name="grupo",
            ),
        ),
        migrations.AddField(
            model_name="restaurant",
            name="nif",
            field=models.CharField(blank=True, max_length=9, validators=[core.validators.validate_nif], verbose_name="NIF"),
        ),
        migrations.AddField(
            model_name="restaurant",
            name="address",
            field=models.CharField(blank=True, max_length=200, verbose_name="morada"),
        ),
        migrations.AddField(
            model_name="restaurant",
            name="municipality",
            field=models.CharField(
                blank=True,
                help_text="Para saber que feriado municipal se aplica.",
                max_length=80,
                verbose_name="concelho",
            ),
        ),
        migrations.RunPython(criar_grupos, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="restaurant",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="restaurants",
                to="core.organization",
                verbose_name="grupo",
            ),
        ),
    ]
