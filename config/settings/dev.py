from .base import *  # noqa: F401,F403

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Em dev os ficheiros estáticos são servidos diretamente, sem manifest.
STORAGES["staticfiles"] = {  # noqa: F405
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Sem scan do STATIC_ROOT em dev (ainda não há collectstatic).
WHITENOISE_AUTOREFRESH = True
