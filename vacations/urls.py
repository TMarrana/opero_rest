from django.urls import path

from . import views

app_name = "vacations"

urlpatterns = [
    path("", views.VacationListView.as_view(), name="lista"),
    path("novo/", views.VacationCreateView.as_view(), name="novo"),
    path("<int:pk>/<str:acao>/", views.VacationDecideView.as_view(), name="decidir"),
]
