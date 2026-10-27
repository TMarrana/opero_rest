from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("", views.AnalysisView.as_view(), name="inicio"),
    path("stock/", views.StockReportView.as_view(), name="stock"),
    path("compras/", views.PurchasesReportView.as_view(), name="compras"),
]
