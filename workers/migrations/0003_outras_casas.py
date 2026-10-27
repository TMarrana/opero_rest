from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_grupo_e_casas"),
        ("workers", "0002_codigo_de_ponto"),
    ]

    operations = [
        migrations.AlterField(
            model_name="worker",
            name="restaurant",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="workers",
                to="core.restaurant",
                verbose_name="casa principal",
            ),
        ),
        migrations.AddField(
            model_name="worker",
            name="other_restaurants",
            field=models.ManyToManyField(
                blank=True, related_name="visiting_workers", to="core.restaurant", verbose_name="também trabalha em"
            ),
        ),
    ]
