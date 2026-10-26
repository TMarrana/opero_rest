from django.urls import path

from . import views

app_name = "kiosk"

urlpatterns = [
    path("", views.NamesView.as_view(), name="inicio"),
    path("<int:pk>/", views.CodeView.as_view(), name="codigo"),
    path("<int:pk>/marcar/", views.MarkView.as_view(), name="marcar"),
]
