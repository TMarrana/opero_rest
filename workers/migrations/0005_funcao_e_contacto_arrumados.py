"""Arruma as fichas que já existem com as regras da Tarefa D5: a função com
maiúscula e os telefones portugueses no formato +351 XXX XXX XXX."""
import re

from django.db import migrations
from django.utils.text import capfirst

# Cópia de workers.formatos.normalizar_contacto (2026-11-07): uma migração
# aplicada não pode mudar de comportamento se a regra mudar mais tarde.
_TELEFONE_PT = re.compile(r"(?:\+351|00351)?([29]\d{8})")


def _contacto(texto):
    texto = (texto or "").strip()
    numero = _TELEFONE_PT.fullmatch(re.sub(r"[\s.()-]", "", texto))
    if not numero:
        return texto
    n = numero.group(1)
    return f"+351 {n[:3]} {n[3:6]} {n[6:]}"


def arrumar_fichas(apps, schema_editor):
    Worker = apps.get_model("workers", "Worker")
    for w in Worker.objects.only("pk", "job_title", "contact"):
        funcao, contacto = capfirst(w.job_title.strip()), _contacto(w.contact)
        if (funcao, contacto) != (w.job_title, w.contact):
            Worker.objects.filter(pk=w.pk).update(job_title=funcao, contact=contacto)


class Migration(migrations.Migration):
    dependencies = [("workers", "0004_worker_end_date")]

    operations = [migrations.RunPython(arrumar_fichas, migrations.RunPython.noop)]
