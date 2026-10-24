from django.urls import path

from . import views

app_name = "shifts"

urlpatterns = [
    path("", views.PlannerView.as_view(), name="planeador"),
    path("celula/<int:worker>/<str:dia>/", views.CellView.as_view(), name="celula"),
    path("lote/", views.BulkView.as_view(), name="lote"),
    path("copiar/", views.CopyWeekView.as_view(), name="copiar"),
    path("publicar/", views.PublishView.as_view(), name="publicar"),
]
