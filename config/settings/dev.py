from .base import *  # noqa: F401,F403

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
# Hosts extra para testar no telemovel via tunel HTTPS (ver .env.example).
ALLOWED_HOSTS += env.list("DJANGO_EXTRA_HOSTS", default=[])  # noqa: F405
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])  # noqa: F405

# Em dev os ficheiros estáticos são servidos diretamente, sem manifest.
STORAGES["staticfiles"] = {  # noqa: F405
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Sem scan do STATIC_ROOT em dev (ainda não há collectstatic).
WHITENOISE_AUTOREFRESH = True

# O WhiteNoise serve os estáticos também no runserver, como em produção. Em
# dev manda max-age=0: o browser pergunta sempre se o CSS ou o JS mudou, em
# vez de reutilizar uma cópia antiga (o runserver não manda Cache-Control).
INSTALLED_APPS = ["whitenoise.runserver_nostatic", *INSTALLED_APPS]  # noqa: F405
