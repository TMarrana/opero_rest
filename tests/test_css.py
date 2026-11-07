import os
import subprocess

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.checks import css_desatualizado


def _ficheiros(tmp_path):
    (tmp_path / "templates").mkdir()
    css = tmp_path / "app.css"
    tpl = tmp_path / "templates" / "x.html"
    css.write_text("a{}")
    tpl.write_text("<p></p>")
    return css, tpl


def test_css_mais_antigo_que_um_template_esta_desatualizado(tmp_path):
    css, tpl = _ficheiros(tmp_path)
    os.utime(css, (1, 1))
    assert css_desatualizado(css, [tmp_path / "templates"]) is True


def test_css_recente_esta_em_dia(tmp_path):
    css, tpl = _ficheiros(tmp_path)
    os.utime(tpl, (1, 1))
    assert css_desatualizado(css, [tmp_path / "templates"]) is False


def test_css_em_falta_esta_desatualizado(tmp_path):
    assert css_desatualizado(tmp_path / "app.css", [tmp_path]) is True


def test_ficheiro_indicado_mais_recente_desatualiza(tmp_path):
    css, tpl = _ficheiros(tmp_path)
    os.utime(tpl, (1, 1))
    cfg = tmp_path / "tailwind.config.js"
    cfg.write_text("module.exports = {}")
    os.utime(css, (1000, 1000))
    os.utime(cfg, (2000, 2000))
    assert css_desatualizado(css, [tmp_path / "templates", cfg]) is True


def test_fontes_inexistentes_sao_ignoradas(tmp_path):
    css, tpl = _ficheiros(tmp_path)
    os.utime(tpl, (1, 1))
    assert css_desatualizado(css, [tmp_path / "nao-existe", tmp_path / "templates"]) is False


def _projeto_com_tailwind(tmp_path, settings, monkeypatch, codigo):
    """Um BASE_DIR com um template e um app.css antigo, e um Tailwind que
    termina com `codigo` sem escrever nada (o que o Tailwind v3 faz quando o
    CSS gerado e igual ao que ja estava no ficheiro)."""
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "x.html").write_text("<p></p>")
    (tmp_path / "static" / "css").mkdir(parents=True)
    css = tmp_path / "static" / "css" / "app.css"
    css.write_text("a{}")
    os.utime(css, (1, 1))
    binario = tmp_path / "tailwindcss"
    binario.write_text("")
    settings.BASE_DIR = tmp_path
    monkeypatch.setenv("TAILWIND_BIN", str(binario))
    monkeypatch.setattr(
        "core.management.commands.css.subprocess.run",
        lambda comando, **kwargs: subprocess.CompletedProcess(comando, codigo),
    )
    return css


def test_compilar_deixa_o_css_em_dia_mesmo_sem_reescrever_o_ficheiro(tmp_path, settings, monkeypatch):
    css = _projeto_com_tailwind(tmp_path, settings, monkeypatch, codigo=0)
    call_command("css")
    assert css_desatualizado(css, [tmp_path / "templates"]) is False


def test_compilacao_falhada_deixa_o_css_desatualizado(tmp_path, settings, monkeypatch):
    css = _projeto_com_tailwind(tmp_path, settings, monkeypatch, codigo=1)
    with pytest.raises(CommandError):
        call_command("css")
    assert css_desatualizado(css, [tmp_path / "templates"]) is True
