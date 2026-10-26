from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core import signing
from django.shortcuts import redirect, render
from django.views import View

from core.mixins import ManagerRequiredMixin
from core.models import WorkArea
from core.utils import restaurant_scope

from .forms import LoginForm

DEVICE_COOKIE = "opero_dispositivo"
DEVICE_MAX_AGE = 60 * 60 * 24 * 180  # 180 dias


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class LogoutView(auth_views.LogoutView):
    pass


class PostLoginRedirectView(LoginRequiredMixin, View):
    """Cada perfil entra na sua superfície (secção 5 do plano)."""

    def get(self, request):
        if request.user.is_backoffice:
            return redirect("dashboard:home")
        return redirect("staff:home")


class SetPasswordView(LoginRequiredMixin, View):
    """Mudar a password provisória que o gerente gerou (Fase 7). Enquanto
    não a mudar, o titular não chega a mais nenhum ecrã
    (`accounts.middleware.ForcePasswordChangeMiddleware`)."""

    template_name = "accounts/definir_password.html"

    def _form(self, request, data=None):
        form = SetPasswordForm(request.user, data)
        form.fields["new_password1"].label = "Nova palavra-passe"
        form.fields["new_password2"].label = "Repita a palavra-passe"
        for campo in form.fields.values():
            campo.widget.attrs.update({"class": "campo-input", "autocomplete": "new-password"})
        return form

    def get(self, request):
        return render(request, self.template_name, {"form": self._form(request)})

    def post(self, request):
        form = self._form(request, request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})
        user = form.save(commit=False)
        user.must_change_password = False
        user.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Palavra-passe guardada")
        return redirect("accounts:pos_login")


def device_info(request):
    """Conteúdo do cookie de dispositivo, ou None se não houver, for
    inválido ou for de um telemóvel pessoal. Desde a Fase 7 só se pica no
    tablet partilhado: um cookie antigo do modo pessoal deixa de abrir o
    quiosque. Os cookies anteriores ao modo quiosque não trazem
    `partilhado` e contam como partilhados. Os anteriores à Fase 7 não
    trazem o restaurante, que se tira de quem ativou."""
    valor = request.COOKIES.get(DEVICE_COOKIE)
    if not valor:
        return None
    try:
        info = signing.loads(valor, salt=DEVICE_COOKIE, max_age=DEVICE_MAX_AGE)
    except signing.BadSignature:
        return None
    if not info.get("partilhado", True):
        return None
    restaurante = info.get("restaurante")
    if restaurante is None and info.get("por"):
        from accounts.models import User

        restaurante = User.objects.filter(pk=info["por"]).values_list("restaurant_id", flat=True).first()
    return {"area": info.get("area"), "restaurante": restaurante}


def device_work_area(request):
    """Área do dispositivo onde se está a marcar, se ainda estiver em uso."""
    info = device_info(request)
    if not info or not info["area"]:
        return None
    return WorkArea.objects.filter(pk=info["area"], archived_at__isnull=True).first()


class DeviceActivateView(ManagerRequiredMixin, View):
    """Ativa este navegador como tablet do restaurante: cookie assinado de
    longa duração que abre o quiosque em /quiosque/ (secção 7 do plano)."""

    def _areas(self, request):
        return restaurant_scope(request.user, WorkArea.objects.filter(archived_at__isnull=True))

    def get(self, request):
        info = device_info(request)
        return render(
            request,
            "accounts/dispositivo.html",
            {
                "ativo": info is not None,
                "area_atual": info["area"] if info else None,
                "areas": self._areas(request),
            },
        )

    def post(self, request):
        resp = redirect("accounts:dispositivo")
        area = self._areas(request).filter(pk=request.POST.get("area") or None).first()
        valor = signing.dumps(
            {
                "por": request.user.pk,
                "partilhado": True,
                "area": area.pk if area else None,
                "restaurante": request.user.restaurant_id,
            },
            salt=DEVICE_COOKIE,
        )
        resp.set_cookie(
            DEVICE_COOKIE,
            valor,
            max_age=DEVICE_MAX_AGE,
            httponly=True,
            samesite="Lax",
            secure=request.is_secure(),
        )
        messages.success(request, "Dispositivo ativado")
        return resp
