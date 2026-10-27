from django.urls import path

from . import consumption_views, count_views, views

app_name = "inventory"

urlpatterns = [
    path("", views.ItemListView.as_view(), name="lista"),
    path("novo/", views.ItemFormView.as_view(), name="novo"),
    path("<int:pk>/editar/", views.ItemFormView.as_view(), name="editar"),
    path("<int:pk>/movimento/", views.MovementCreateView.as_view(), name="movimento"),
    path("<int:pk>/transferir/", views.TransferView.as_view(), name="transferir"),
    path("historico/", views.HistoryView.as_view(), name="historico"),
    path("consumos/", consumption_views.ConsumptionListView.as_view(), name="consumos"),
    path("consumos/novo/", consumption_views.ConsumptionCreateView.as_view(), name="consumo_novo"),
    path("consumos/regras/", consumption_views.ConsumptionSettingsView.as_view(), name="consumo_regras"),
    path("consumos/<int:pk>/anular/", consumption_views.ConsumptionCancelView.as_view(), name="consumo_anular"),
    path("contagens/", count_views.CountListView.as_view(), name="contagens"),
    path("contagens/contar/", count_views.CountSheetView.as_view(), name="contagem"),
    path("categorias/", views.CategoryListView.as_view(), name="categorias"),
    path("categorias/<int:pk>/editar/", views.CategoryUpdateView.as_view(), name="categoria_editar"),
    path("categorias/<int:pk>/eliminar/", views.CategoryDeleteView.as_view(), name="categoria_eliminar"),
]
