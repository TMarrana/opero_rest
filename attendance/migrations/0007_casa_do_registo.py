"""Fase 9: o registo de ponto e o pedido de correção guardam a casa. Os que
já existem ficam na casa principal do trabalhador, a única onde se picava."""
from django.db import migrations, models
from django.db.models import OuterRef, Subquery


def preencher(apps, schema_editor):
    TimeEntry = apps.get_model("attendance", "TimeEntry")
    CorrectionRequest = apps.get_model("attendance", "CorrectionRequest")
    Worker = apps.get_model("workers", "Worker")
    casa = Subquery(Worker.objects.filter(pk=OuterRef("worker_id")).values("restaurant_id")[:1])
    TimeEntry.objects.update(restaurant_id=casa)
    CorrectionRequest.objects.update(restaurant_id=casa)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_grupo_e_casas"),
        ("workers", "0003_outras_casas"),
        ("attendance", "0006_fecho_do_mes"),
    ]

    operations = [
        migrations.AddField(
            model_name="timeentry",
            name="restaurant",
            field=models.ForeignKey(
                null=True, on_delete=models.deletion.CASCADE, related_name="time_entries",
                to="core.restaurant", verbose_name="casa",
            ),
        ),
        migrations.AddField(
            model_name="correctionrequest",
            name="restaurant",
            field=models.ForeignKey(
                null=True, on_delete=models.deletion.CASCADE, related_name="correction_requests",
                to="core.restaurant", verbose_name="casa",
            ),
        ),
        migrations.RunPython(preencher, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="timeentry",
            name="restaurant",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name="time_entries",
                to="core.restaurant", verbose_name="casa",
            ),
        ),
        migrations.AlterField(
            model_name="correctionrequest",
            name="restaurant",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name="correction_requests",
                to="core.restaurant", verbose_name="casa",
            ),
        ),
    ]
