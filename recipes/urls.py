from django.urls import path

from . import views

app_name = "recipes"

urlpatterns = [
    path("", views.RecipeListView.as_view(), name="lista"),
    path("nova/", views.RecipeFormView.as_view(), name="nova"),
    path("<int:pk>/", views.RecipeDetailView.as_view(), name="ficha"),
    path("<int:pk>/editar/", views.RecipeFormView.as_view(), name="editar"),
    path("<int:pk>/imprimir/", views.RecipePrintView.as_view(), name="imprimir"),
    path("pos/", views.PosProductsView.as_view(), name="pos"),
]
