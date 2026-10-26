"""Fase 7: o código de ponto passa do utilizador para a ficha do
trabalhador. Os PINs já definidos são copiados tal como estão (o hash
serve igual); `accounts/0003` remove depois os campos do utilizador."""
from django.db import migrations, models


def copiar_pins(apps, schema_editor):
    Worker = apps.get_model("workers", "Worker")
    for worker in Worker.objects.filter(user__staff_pin__isnull=False).select_related("user"):
        worker.kiosk_code = worker.user.staff_pin
        worker.code_set_at = worker.user.pin_set_at
        worker.save(update_fields=["kiosk_code", "code_set_at"])


def devolver_pins(apps, schema_editor):
    Worker = apps.get_model("workers", "Worker")
    for worker in Worker.objects.filter(kiosk_code__isnull=False, user__isnull=False).select_related("user"):
        worker.user.staff_pin = worker.kiosk_code
        worker.user.pin_set_at = worker.code_set_at
        worker.user.save(update_fields=["staff_pin", "pin_set_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("workers", "0001_initial"),
        ("accounts", "0002_groups_por_perfil"),
    ]

    operations = [
        migrations.AddField(
            model_name="worker",
            name="kiosk_code",
            field=models.CharField(blank=True, editable=False, max_length=128, null=True),
        ),
        migrations.AddField(
            model_name="worker",
            name="code_set_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(copiar_pins, devolver_pins),
    ]
