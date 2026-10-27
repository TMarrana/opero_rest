"""
Grupo do endereço e casa ativa do pedido.

Isolamento entre clientes (decidido a 2026-10-27): com OPERO_BASE_DOMAIN,
cada grupo entra em <endereço>.<domínio>. `OrganizationHostMiddleware`
põe o grupo em `request.organization` e põe fora uma sessão de outro
grupo. É uma segunda barreira: as views continuam a filtrar pela casa.

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
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

from .models import Organization

SESSION_KEY = "opero_casa"
HEADER = "X-Opero-Casa"
FIELD = "_casa"


# O endereço do domínio base sem grupo: o site e a página para encontrar o
# endereço do restaurante.
SEM_GRUPO = ("www", "app")


def subdomain_of(host, base):
    """O subdomínio de `host` debaixo de `base`, ou None no próprio domínio,
    em www e app, e fora dele."""
    host = host.split(":")[0].lower().rstrip(".")
    if not host.endswith("." + base):
        return None
    sub = host[: -len(base) - 1]
    return None if sub in SEM_GRUPO else sub


def group_url(request, grupo, path="/"):
    """O endereço completo de um caminho no subdomínio do grupo."""
    porta = request.get_port()
    porta = "" if porta in ("80", "443") else f":{porta}"
    return f"{request.scheme}://{grupo.subdomain}.{settings.OPERO_BASE_DOMAIN}{porta}{path}"


class OrganizationHostMiddleware:
    # No domínio sem grupo só há a página do endereço, o admin da
    # plataforma e os estáticos.
    LIVRES_SEM_GRUPO = ("/admin/", "/static/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.organization = None
        base = settings.OPERO_BASE_DOMAIN
        if not base:
            return self.get_response(request)
        sub = subdomain_of(request.get_host(), base)
        if sub is None:
            endereco = reverse("accounts:endereco")
            if request.path != endereco and not request.path.startswith(self.LIVRES_SEM_GRUPO):
                return redirect(endereco)
            return self.get_response(request)
        grupo = Organization.objects.filter(subdomain=sub, is_active=True).first()
        if grupo is None:
            raise Http404("Não há nenhum restaurante neste endereço.")
        request.organization = grupo
        user = request.user
        if user.is_authenticated and not user.is_superuser and user.organization_id != grupo.pk:
            logout(request)
            return redirect("accounts:login")
        return self.get_response(request)


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
