from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    """Quem entrou com uma password provisória só chega ao ecrã de a
    mudar, na app e no backoffice (Fase 7). Sair continua possível, e os
    estáticos e o service worker não passam por aqui."""

    LIVRES = ("/static/", "/sw.js")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.must_change_password:
            permitidos = {reverse("accounts:definir_password"), reverse("accounts:logout")}
            if request.path not in permitidos and not request.path.startswith(self.LIVRES):
                return redirect("accounts:definir_password")
        return self.get_response(request)
