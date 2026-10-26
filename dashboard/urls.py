from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="home"),
    path("casa/", views.SwitchRestaurantView.as_view(), name="mudar_casa"),
]
