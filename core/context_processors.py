from django.utils.functional import SimpleLazyObject

# Secção do rail do backoffice em que cada página vive, pelo início do endereço.
_SECOES = (
    ("/gestao/grupo/", "grupo"),
    ("/gestao/trabalhadores/", "trabalhadores"),
    ("/gestao/ponto/", "ponto"),
    ("/gestao/ferias/", "ferias"),
    ("/gestao/turnos/", "turnos"),
    ("/gestao/stock/", "stock"),
    ("/gestao/compras/", "compras"),
    ("/gestao/fichas/", "fichas"),
    ("/gestao/vendas/", "vendas"),
    ("/gestao/analise/", "analise"),
    ("/gestao/configuracao/", "configuracao"),
    ("/conta/dispositivo/", "dispositivo"),
)


def casa(request):
    """Perfil na casa ativa (Fase 9), secção ativa do rail e contadores da
    navegação. Os contadores só se calculam se o template os usar."""
    from accounts.models import User

    role = getattr(request, "role", None)
    ctx = {"perfil_ativo": User.Role(role).label if role else "", "nav_secao": _secao(request.path)}
    if role and getattr(request, "restaurant", None) is not None:
        ctx["contadores"] = SimpleLazyObject(lambda: _contadores(request))
    return ctx


def _secao(path):
    if path == "/gestao/":
        return "dashboard"
    return next((chave for prefixo, chave in _SECOES if path.startswith(prefixo)), "")


def _contadores(request):
    """O que está por tratar em cada área, com os mesmos critérios do
    dashboard, para se ver de qualquer página. As áreas de pessoas só contam
    para quem as pode abrir (matriz da secção 7)."""
    from django.db.models import F

    from attendance.models import CorrectionRequest, TimeEntry
    from core.utils import restaurant_scope
    from inventory.models import Item
    from vacations.models import VacationRequest

    contadores = {
        "stock": restaurant_scope(request, Item.objects.filter(is_active=True))
        .filter(current_stock__lte=F("minimum_stock"))
        .count(),
    }
    if request.role in ("ADMIN", "MANAGER"):
        pedidos = restaurant_scope(
            request, CorrectionRequest.objects.filter(status=CorrectionRequest.Status.PENDENTE)
        ).count()
        por_resolver = restaurant_scope(request, TimeEntry.objects.all()).unresolved().count()
        contadores["ponto"] = pedidos + por_resolver
        contadores["ferias"] = restaurant_scope(
            request,
            VacationRequest.objects.filter(status=VacationRequest.Status.PENDENTE),
            field="worker__restaurant",
        ).count()
    return contadores
