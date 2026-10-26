from django.urls import path

from . import views

app_name = "workers"

urlpatterns = [
    path("", views.WorkerListView.as_view(), name="lista"),
    path("novo/", views.WorkerFormView.as_view(), name="novo"),
    path("<int:pk>/editar/", views.WorkerFormView.as_view(), name="editar"),
    path("<int:pk>/codigo/", views.WorkerCodeView.as_view(), name="codigo"),
    path("<int:pk>/conta/", views.WorkerAccountView.as_view(), name="conta"),
]
