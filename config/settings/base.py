"""
Settings base do Opero Rest.

Nada aqui depende do ambiente. O que varia (DEBUG, BD, hosts, segredos)
vive em dev.py / prod.py e no ficheiro .env — ver .env.example.
"""
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
# Lê .env se existir; em produção as variáveis vêm do ambiente real.
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="inseguro-so-para-dev")

DEBUG = False

ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # apps do projeto
    "core",
    "accounts",
    "workers",
    "attendance",
    "vacations",
    "shifts",
    "inventory",
    "dashboard",
    "staff",
    "kiosk",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "accounts.middleware.ForcePasswordChangeMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": env.db_url("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:pos_login"
LOGOUT_REDIRECT_URL = "accounts:login"

LANGUAGE_CODE = "pt-pt"
TIME_ZONE = "Europe/Lisbon"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Ponto (Fase 5). Horas a partir das quais uma entrada sem saída fica por
# resolver e deixa de contar para os totais (R-013). Valor provisório,
# a decidir com a AT (secção 12 do plano).
ATTENDANCE_UNRESOLVED_HOURS = 14

# Dias úteis de férias por ano quando o trabalhador não tem saldo definido
# (Fase 5). O valor do Código do Trabalho, por validar com a AT (Q-008).
VACATION_DEFAULT_DAYS = 22

# Planeador de turnos (Fase 6).
# Descanso mínimo entre o fim de um turno e o início do seguinte. Por
# confirmar com a AT (Q-001); a Factorial só aplica a regra no Enterprise.
SHIFT_MIN_REST_HOURS = 11
# Com turno publicado, uma entrada sem saída fica por resolver estas horas
# depois do fim previsto do turno (substitui o limite fixo da Fase 5).
SHIFT_UNRESOLVED_MARGIN_HOURS = 4
# Minutos de tolerância antes de assinalar um atraso ou uma saída fora do
# previsto na vista da equipa.
SHIFT_TOLERANCE_MINUTES = 10
