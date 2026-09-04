from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("componentes/", views.ComponentsView.as_view(), name="components"),
    path("sw.js", views.service_worker, name="sw"),
]
