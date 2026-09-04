from django.urls import path

from accounts.views import WorkerPinView

from . import views

app_name = "workers"

urlpatterns = [
    path("", views.WorkerListView.as_view(), name="lista"),
    path("novo/", views.WorkerFormView.as_view(), name="novo"),
    path("<int:pk>/editar/", views.WorkerFormView.as_view(), name="editar"),
    path("<int:pk>/pin/", WorkerPinView.as_view(), name="pin"),
]
