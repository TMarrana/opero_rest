"""Aviso quando static/css/app.css (compilado, fora do git) fica para tras das fontes."""
from pathlib import Path

from django.conf import settings
from django.core.checks import Tags, Warning, register


def _mtime_mais_recente(fontes):
    """O st_mtime mais recente entre ficheiros e `*.html` (recursivo) das pastas; 0 se nada existir."""
    mais_recente = 0.0
    for fonte in fontes:
        fonte = Path(fonte)
        if fonte.is_dir():
            ficheiros = fonte.rglob("*.html")
        elif fonte.is_file():
            ficheiros = [fonte]
        else:
            continue
        for ficheiro in ficheiros:
            mais_recente = max(mais_recente, ficheiro.stat().st_mtime)
    return mais_recente


def css_desatualizado(css, fontes):
    """True se o CSS nao existe ou e mais antigo do que alguma das fontes."""
    css = Path(css)
    if not css.is_file():
        return True
    return css.stat().st_mtime < _mtime_mais_recente(fontes)


@register(Tags.staticfiles)
def avisar_css_desatualizado(app_configs, **kwargs):
    if not settings.DEBUG:
        return []
    base = Path(settings.BASE_DIR)
    fontes = [
        base / "templates",
        base / "static" / "src" / "input.css",
        base / "tailwind.config.js",
        *base.glob("*/templates"),
    ]
    if not css_desatualizado(base / "static" / "css" / "app.css", fontes):
        return []
    return [
        Warning(
            "O CSS está desatualizado. Corra: python manage.py css",
            id="opero.W001",
        )
    ]
