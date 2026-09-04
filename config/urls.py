from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("conta/", include("accounts.urls")),
    path("gestao/", include("dashboard.urls")),
    path("equipa/", include("staff.urls")),
    path("", include("core.urls")),
    path("", lambda request: redirect("accounts:pos_login"), name="root"),
]
