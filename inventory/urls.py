from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("", views.ItemListView.as_view(), name="lista"),
    path("novo/", views.ItemFormView.as_view(), name="novo"),
    path("<int:pk>/editar/", views.ItemFormView.as_view(), name="editar"),
    path("<int:pk>/movimento/", views.MovementCreateView.as_view(), name="movimento"),
    path("historico/", views.HistoryView.as_view(), name="historico"),
    path("categorias/", views.CategoryListView.as_view(), name="categorias"),
    path("categorias/<int:pk>/editar/", views.CategoryUpdateView.as_view(), name="categoria_editar"),
    path("categorias/<int:pk>/eliminar/", views.CategoryDeleteView.as_view(), name="categoria_eliminar"),
]
