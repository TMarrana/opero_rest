from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("entrar/", views.LoginView.as_view(), name="login"),
    path("sair/", views.LogoutView.as_view(), name="logout"),
    path("pos-login/", views.PostLoginRedirectView.as_view(), name="pos_login"),
    path("dispositivo/", views.DeviceActivateView.as_view(), name="dispositivo"),
]
