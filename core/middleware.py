"""
Casa ativa do pedido (Fase 9).

Cada pedido do backoffice trabalha numa só casa: `request.restaurant` é a
casa e `request.role` o perfil dessa conta nela. As views filtram sempre
por `request.restaurant` (`core.utils.restaurant_scope`); quem não tem
acesso a nenhuma casa fica com os dois a None e os mixins recusam-no.

A casa escolhida fica na sessão, que é partilhada pelos separadores. Por
isso cada página do backoffice manda a casa em que foi aberta
(`X-Opero-Casa` nos pedidos HTMX, `_casa` nos formulários, ver
`base_manage.html`): um POST de uma página aberta noutra casa é recusado
antes de gravar o que quer que seja.
"""
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

SESSION_KEY = "opero_casa"
HEADER = "X-Opero-Casa"
FIELD = "_casa"


def casa_ativa(user, session):
    """(restaurante, perfil, {restaurante: perfil}) para esta conta. A casa
    da sessão, se ainda tiver acesso a ela; senão a casa por omissão; senão
    a primeira por ordem do nome."""
    casas = user.casas()
    if not casas:
        return None, None, casas
    por_pk = {r.pk: r for r in casas}
    escolhida = por_pk.get(session.get(SESSION_KEY)) or por_pk.get(user.restaurant_id) or next(iter(casas))
    return escolhida, casas[escolhida], casas


class ActiveRestaurantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.restaurant, request.role, request.casas = None, None, {}
        if request.user.is_authenticated:
            request.restaurant, request.role, request.casas = casa_ativa(request.user, request.session)
            if self._de_outra_casa(request):
                return self._recusar(request)
        return self.get_response(request)

    def _de_outra_casa(self, request):
        if request.method != "POST" or request.restaurant is None:
            return False
        if request.path == reverse("dashboard:mudar_casa"):
            return False
        enviada = request.headers.get(HEADER) or request.POST.get(FIELD)
        return bool(enviada) and enviada != str(request.restaurant.pk)

    def _recusar(self, request):
        messages.error(
            request,
            f"Mudou para {request.restaurant} noutro separador. Nada foi gravado: confirme a casa e repita.",
        )
        destino = reverse("dashboard:home")
        if request.headers.get("HX-Request"):
            resp = HttpResponse(status=409)
            resp["HX-Redirect"] = destino
            return resp
        return redirect(destino)
