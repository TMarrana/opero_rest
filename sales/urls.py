from django.urls import path

from . import views

app_name = "sales"

urlpatterns = [
    path("", views.SalesView.as_view(), name="vendas"),
    path("importar/", views.ImportView.as_view(), name="importar"),
    path("regras/", views.SettingsView.as_view(), name="regras"),
]
