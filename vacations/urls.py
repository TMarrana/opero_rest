from django.urls import path

from . import views

app_name = "vacations"

urlpatterns = [
    path("", views.VacationListView.as_view(), name="lista"),
    path("novo/", views.VacationCreateView.as_view(), name="novo"),
    path("saldos/", views.AllowanceListView.as_view(), name="saldos"),
    path("calendario/", views.CalendarView.as_view(), name="calendario"),
    path("calendario/<int:worker>/<str:dia>/", views.CalendarCellView.as_view(), name="celula"),
    path("<int:pk>/<str:acao>/", views.VacationDecideView.as_view(), name="decidir"),
]
