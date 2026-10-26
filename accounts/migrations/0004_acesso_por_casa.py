"""Fase 9: acesso por casa e Admin do grupo.

Cada conta com restaurante fica com o acesso a essa casa, com o perfil que
tinha. Um superuser sem restaurante via tudo enquanto havia um só
restaurante; se houver um só grupo, passa a Admin desse grupo, para não
perder o acesso que já tinha."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def acessos(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Membership = apps.get_model("accounts", "Membership")
    Organization = apps.get_model("core", "Organization")
    for user in User.objects.filter(restaurant__isnull=False).select_related("restaurant"):
        user.organization_id = user.restaurant.organization_id
        user.save(update_fields=["organization"])
        Membership.objects.get_or_create(user=user, restaurant_id=user.restaurant_id, defaults={"role": user.role})
    grupos = list(Organization.objects.all()[:2])
    if len(grupos) == 1:
        User.objects.filter(restaurant__isnull=True, is_superuser=True).update(
            organization=grupos[0], is_group_admin=True
        )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_password_provisoria_sem_pin"),
        ("core", "0003_grupo_e_casas"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="users",
                to="core.organization",
                verbose_name="grupo",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="is_group_admin",
            field=models.BooleanField(default=False, verbose_name="admin do grupo"),
        ),
        migrations.CreateModel(
            name="Membership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("ADMIN", "Administrador"),
                            ("MANAGER", "Gerente"),
                            ("STOCK", "Responsável de stock"),
                            ("STAFF", "Colaborador"),
                        ],
                        max_length=10,
                        verbose_name="perfil",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                (
                    "restaurant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="core.restaurant",
                        verbose_name="restaurante",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="utilizador",
                    ),
                ),
            ],
            options={
                "verbose_name": "acesso a casa",
                "verbose_name_plural": "acessos a casas",
                "constraints": [models.UniqueConstraint(fields=("user", "restaurant"), name="um_acesso_por_casa")],
            },
        ),
        migrations.RunPython(acessos, migrations.RunPython.noop),
    ]
