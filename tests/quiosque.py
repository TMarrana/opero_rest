"""Ajudas para os testes que picam o ponto no quiosque (Fase 7)."""
from django.urls import reverse


def ativar_tablet(client, gerente, area=None):
    """O gerente ativa este navegador como tablet e sai: o quiosque fica
    sem sessão, como no restaurante."""
    client.force_login(gerente)
    client.post(reverse("accounts:dispositivo"), {"area": area.pk} if area is not None else {})
    client.post(reverse("accounts:logout"))


def escrever_codigo(client, worker, codigo="2468"):
    return client.post(reverse("kiosk:codigo", args=[worker.pk]), {"codigo": codigo})


def picar(client, worker, acao, codigo="2468", **extra):
    """Nome → código → ação. Devolve a resposta da confirmação."""
    resp = escrever_codigo(client, worker, codigo)
    token = resp.context["token"]
    return client.post(reverse("kiosk:marcar", args=[worker.pk]), {"token": token, "acao": acao, **extra})
