from django.urls import path

from accounts.views import StaffLoginView

from . import views

app_name = "staff"

urlpatterns = [
    path("", views.StaffHomeView.as_view(), name="home"),
    path("entrar/", StaffLoginView.as_view(), name="pin_login"),
    path("marcar/", views.MarkView.as_view(), name="marcar"),
    path("historico/", views.StaffHistoryView.as_view(), name="historico"),
    path("ferias/", views.StaffVacationsView.as_view(), name="ferias"),
    path("correcao/", views.StaffCorrectionView.as_view(), name="correcao_nova"),
    path("correcao/<int:pk>/", views.StaffCorrectionView.as_view(), name="correcao"),
]
