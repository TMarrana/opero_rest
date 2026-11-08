from .base import *  # noqa: F401,F403

DEBUG = False

SECRET_KEY = env("DJANGO_SECRET_KEY")  # noqa: F405 — obrigatório em produção
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")  # noqa: F405

# Atrás do proxy do alojamento: o HTTPS termina lá e chega aqui como
# X-Forwarded-Proto. Sem isto o SECURE_SSL_REDIRECT entra em ciclo.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# Os grupos entram em <endereço>.opero.pt; o CSRF tem de os aceitar.
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])  # noqa: F405

# Cache partilhada entre os processos do gunicorn (limite de tentativas e
# tokens do quiosque). A tabela cria-se no migrate (core/migrations/0005).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "opero_cache",
    }
}

# Cópia, para não alterar o dicionário partilhado com o base.py.
DATABASES = {  # noqa: F405
    "default": {
        **DATABASES["default"],  # noqa: F405
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}

# Erros para o Sentry, só se houver DSN. Sem dados pessoais nem as variáveis
# locais do erro (podiam ter nomes e códigos de ponto).
SENTRY_DSN = env("SENTRY_DSN", default="")  # noqa: F405
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(dsn=SENTRY_DSN, send_default_pii=False, include_local_variables=False, traces_sample_rate=0)

CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
