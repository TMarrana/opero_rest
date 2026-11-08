import importlib

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


def _prod(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "x" * 60)
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", ".opero.pt")
    monkeypatch.setenv("DJANGO_CSRF_TRUSTED_ORIGINS", "https://*.opero.pt")
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    import config.settings.prod as prod

    return importlib.reload(prod)


def test_prod_atras_de_proxy_https(monkeypatch):
    prod = _prod(monkeypatch)
    assert prod.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
    assert prod.CSRF_TRUSTED_ORIGINS == ["https://*.opero.pt"]


def test_prod_cache_partilhada_entre_processos(monkeypatch):
    prod = _prod(monkeypatch)
    assert prod.CACHES["default"]["BACKEND"] == "django.core.cache.backends.db.DatabaseCache"
    assert prod.CACHES["default"]["LOCATION"] == "opero_cache"


def test_prod_ligacoes_a_bd_reutilizadas(monkeypatch):
    prod = _prod(monkeypatch)
    assert prod.DATABASES["default"]["CONN_MAX_AGE"] == 60
    assert prod.DATABASES["default"]["CONN_HEALTH_CHECKS"] is True


def test_demo_recusa_fora_de_desenvolvimento(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="desenvolvimento"):
        call_command("demo")


def test_prod_sentry_sem_dados_pessoais_nem_variaveis_locais(monkeypatch):
    """As variaveis locais de um erro podem ter nomes e codigos de ponto."""
    chamadas = []
    monkeypatch.setattr("sentry_sdk.init", lambda **kw: chamadas.append(kw))
    monkeypatch.setenv("SENTRY_DSN", "https://chave@sentry.example/1")
    monkeypatch.setenv("DJANGO_SECRET_KEY", "x" * 60)
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", ".opero.pt")
    import config.settings.prod as prod

    importlib.reload(prod)
    [kw] = chamadas
    assert kw["send_default_pii"] is False and kw["include_local_variables"] is False


def test_demo_com_forcar_corre_fora_de_desenvolvimento(settings, db):
    from accounts.models import User

    settings.DEBUG = False
    call_command("demo", forcar=True)
    assert User.objects.filter(email="gerente@tasca.pt").exists()


def test_migracao_cria_a_tabela_da_cache(monkeypatch):
    """Sem a tabela, o limite de tentativas do login da 500 em producao."""
    modulo = importlib.import_module("core.migrations.0005_tabela_da_cache")
    chamadas = []
    monkeypatch.setattr(modulo, "call_command", lambda *a, **k: chamadas.append(a))
    modulo.criar_tabela_da_cache(None, None)
    assert chamadas == [("createcachetable",)]
