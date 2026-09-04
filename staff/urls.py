from django.urls import path

from . import views

app_name = "staff"

urlpatterns = [
    path("", views.StaffHomeView.as_view(), name="home"),
]
