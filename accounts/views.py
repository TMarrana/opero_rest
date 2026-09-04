from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views import View

from .forms import LoginForm


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
