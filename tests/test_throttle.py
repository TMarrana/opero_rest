"""core.throttle: o contador de falhas que o login e o quiosque usam."""
from core.throttle import Limite


def test_bloqueia_ao_chegar_ao_maximo():
    limite = Limite("t-max", 3, 60)
    for _ in range(2):
        limite.falhou("a")
    assert not limite.bloqueado("a")
    assert limite.falhou("a") == 3
    assert limite.bloqueado("a")


def test_chaves_e_prefixos_sao_independentes():
    a, b = Limite("t-a", 1, 60), Limite("t-b", 1, 60)
    a.falhou("x")
    assert a.bloqueado("x") and not a.bloqueado("y") and not b.bloqueado("x")


def test_limpar_desbloqueia():
    limite = Limite("t-limpar", 1, 60)
    limite.falhou("a")
    limite.limpar("a")
    assert not limite.bloqueado("a")


def test_cada_falha_renova_o_prazo(monkeypatch):
    from django.core.cache import cache

    limite = Limite("t-prazo", 5, 60)
    prazos = []
    monkeypatch.setattr(cache, "touch", lambda k, t: prazos.append(t) or True)
    limite.falhou("a")
    limite.falhou("a")
    assert prazos == [60, 60]
