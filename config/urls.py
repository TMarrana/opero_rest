from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("conta/", include("accounts.urls")),
    path("gestao/grupo/", include("core.group_urls")),
    path("gestao/", include("dashboard.urls")),
    path("gestao/stock/", include("inventory.urls")),
    path("gestao/trabalhadores/", include("workers.urls")),
    path("gestao/ponto/", include("attendance.urls")),
    path("gestao/ferias/", include("vacations.urls")),
    path("gestao/configuracao/", include("core.config_urls")),
    path("gestao/turnos/", include("shifts.urls")),
    path("gestao/vendas/", include("sales.urls")),
    path("gestao/compras/", include("purchasing.urls")),
    path("gestao/fichas/", include("recipes.urls")),
    path("gestao/analise/", include("analytics.urls")),
    path("equipa/", include("staff.urls")),
    path("quiosque/", include("kiosk.urls")),
    path("", include("core.urls")),
    path("", lambda request: redirect("accounts:pos_login"), name="root"),
]
