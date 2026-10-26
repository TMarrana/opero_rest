"""Fase 7: o PIN sai do utilizador (já copiado para a ficha do
trabalhador em `workers/0002`) e entra a password provisória."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_groups_por_perfil"),
        ("workers", "0002_codigo_de_ponto"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="must_change_password",
            field=models.BooleanField(default=False, verbose_name="tem de mudar a password"),
        ),
        migrations.RemoveField(model_name="user", name="staff_pin"),
        migrations.RemoveField(model_name="user", name="pin_set_at"),
    ]
