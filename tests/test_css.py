import os

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
