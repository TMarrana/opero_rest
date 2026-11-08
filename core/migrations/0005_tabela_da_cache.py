"""Cria a tabela da cache partilhada de producao (DatabaseCache, opero_cache),
para o deploy nao depender de alguem se lembrar de correr createcachetable:
sem ela, o limite de tentativas do login da 500. Com outra cache (dev,
testes), o createcachetable nao faz nada."""
from django.core.management import call_command
from django.db import migrations


def criar_tabela_da_cache(apps, schema_editor):
    call_command("createcachetable")


class Migration(migrations.Migration):
    dependencies = [("core", "0004_endereco_do_grupo")]

    operations = [migrations.RunPython(criar_tabela_da_cache, migrations.RunPython.noop)]
