from django import forms
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core import signing
from django.shortcuts import redirect, render
from django.views import View

from core.mixins import PIN_SESSION_KEY, ManagerRequiredMixin
from core.utils import restaurant_scope
from workers.models import Worker

from . import pin as pin_throttle
from .forms import LoginForm

DEVICE_COOKIE = "opero_dispositivo"
DEVICE_MAX_AGE = 60 * 60 * 24 * 180  # 180 dias
PIN_SESSION_AGE = 60 * 60 * 12  # sessões por PIN expiram em 12 horas


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class LogoutView(auth_views.LogoutView):
    pass


class PostLoginRedirectView(LoginRequiredMixin, View):
    """Cada perfil entra na sua superfície (secção 5 do plano)."""

    def get(self, request):
        if request.session.get(PIN_SESSION_KEY):
            return redirect("staff:home")
        if request.user.is_backoffice:
            return redirect("dashboard:home")
        return redirect("staff:home")


def _device_ok(request):
    valor = request.COOKIES.get(DEVICE_COOKIE)
    if not valor:
        return False
    try:
        signing.loads(valor, salt=DEVICE_COOKIE, max_age=DEVICE_MAX_AGE)
        return True
    except signing.BadSignature:
        return False


class DeviceActivateView(ManagerRequiredMixin, View):
    """Ativa este navegador como dispositivo do restaurante: cookie
    assinado de longa duração que dá acesso ao ecrã de login por PIN
    (secção 7 do plano)."""

    def get(self, request):
        return render(request, "accounts/dispositivo.html", {"ativo": _device_ok(request)})

    def post(self, request):
        resp = redirect("accounts:dispositivo")
        valor = signing.dumps({"por": request.user.pk}, salt=DEVICE_COOKIE)
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


class StaffLoginView(View):
    """Seleção de trabalhador + PIN, só em dispositivos ativados.
    A sessão criada fica marcada como PIN e nunca abre o backoffice."""

    def _workers(self, request):
        qs = Worker.objects.filter(is_active=True, user__isnull=False, user__staff_pin__isnull=False)
        return qs.select_related("user").order_by("full_name")

    def get(self, request):
        if not _device_ok(request):
            return render(request, "accounts/pin_dispositivo_em_falta.html", status=403)
        return render(request, "accounts/pin_login.html", {"workers": self._workers(request)})

    def post(self, request):
        if not _device_ok(request):
            return render(request, "accounts/pin_dispositivo_em_falta.html", status=403)
        workers = self._workers(request)
        worker = workers.filter(pk=request.POST.get("worker", "")).first()
        raw_pin = request.POST.get("pin", "")
        erro = None
        if worker is None:
            erro = "Escolha quem é que está a marcar."
        else:
            if not request.session.session_key:
                request.session.save()
            chave_sessao = request.session.session_key
            if pin_throttle.esta_bloqueado(chave_sessao, worker.pk):
                erro = "Demasiadas tentativas. Aguarde um minuto e tente de novo."
            elif not worker.user.check_staff_pin(raw_pin):
                pin_throttle.registar_falha(chave_sessao, worker.pk)
                erro = "PIN errado. Tente de novo."
        if erro:
            return render(
                request,
                "accounts/pin_login.html",
                {"workers": workers, "erro": erro, "worker_escolhido": request.POST.get("worker", "")},
            )
        pin_throttle.limpar_falhas(request.session.session_key, worker.pk)
        auth_login(request, worker.user)
        # Marcar a sessão como PIN DEPOIS do login (login faz flush da sessão).
        request.session[PIN_SESSION_KEY] = True
        request.session.set_expiry(PIN_SESSION_AGE)
        return redirect("staff:home")


class _PinForm(forms.Form):
    pin = forms.RegexField(
        regex=r"^\d{4,6}$",
        label="PIN",
        error_messages={"invalid": "O PIN são 4 a 6 algarismos."},
        widget=forms.PasswordInput(
            attrs={
                "class": "campo-input font-dados",
                "inputmode": "numeric",
                "autocomplete": "off",
                "placeholder": "••••",
            }
        ),
    )


class WorkerPinView(ManagerRequiredMixin, View):
    """Definir ou repor o PIN de um trabalhador (feito pelo gerente)."""

    def _get_worker(self, request, pk):
        from django.shortcuts import get_object_or_404

        return get_object_or_404(restaurant_scope(request.user, Worker.objects.select_related("user")), pk=pk)

    def get(self, request, pk):
        worker = self._get_worker(request, pk)
        return render(request, "manage/workers/pin.html", {"worker": worker, "form": _PinForm()})

    def post(self, request, pk):
        worker = self._get_worker(request, pk)
        if worker.user is None:
            messages.error(request, "Este trabalhador não tem conta de acesso. Associe uma primeiro.")
            return redirect("workers:editar", pk=worker.pk)
        form = _PinForm(request.POST)
        if not form.is_valid():
            return render(request, "manage/workers/pin.html", {"worker": worker, "form": form})
        worker.user.set_staff_pin(form.cleaned_data["pin"])
        messages.success(request, "PIN definido")
        return redirect("workers:lista")
