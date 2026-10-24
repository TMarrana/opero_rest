from django.urls import path

from . import config_views as views

app_name = "config"

urlpatterns = [
    path("", views.ConfigHomeView.as_view(), name="inicio"),
    path("<str:secao>/", views.ConfigListView.as_view(), name="lista"),
    path("<str:secao>/novo/", views.ConfigFormView.as_view(), name="novo"),
    path("<str:secao>/<int:pk>/", views.ConfigFormView.as_view(), name="editar"),
    path("<str:secao>/<int:pk>/remover/", views.ConfigRemoveView.as_view(), name="remover"),
]
