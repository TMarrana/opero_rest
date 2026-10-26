from django.urls import path

from dashboard.views import GroupDashboardView

from . import group_views as views

app_name = "grupo"

urlpatterns = [
    path("", GroupDashboardView.as_view(), name="painel"),
    path("casas/", views.RestaurantListView.as_view(), name="casas"),
    path("casas/nova/", views.RestaurantFormView.as_view(), name="nova_casa"),
    path("casas/<int:pk>/", views.RestaurantFormView.as_view(), name="editar_casa"),
    path("casas/<int:pk>/acessos/", views.AccessView.as_view(), name="acessos"),
]
