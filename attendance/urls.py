from django.urls import path

from . import views

app_name = "attendance"

urlpatterns = [
    path("", views.TeamDayView.as_view(), name="dia"),
    path("registo/<int:pk>/corrigir/", views.EntryCorrectionView.as_view(), name="corrigir"),
    path("trabalhador/<int:pk>/acrescentar/", views.EntryAddView.as_view(), name="acrescentar"),
]
