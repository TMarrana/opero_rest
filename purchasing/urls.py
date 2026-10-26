from django.urls import path

from . import views

app_name = "purchasing"

urlpatterns = [
    path("", views.ShoppingListView.as_view(), name="lista"),
    path("encomendas/", views.OrderListView.as_view(), name="encomendas"),
    path("encomendas/nova/", views.OrderCreateView.as_view(), name="encomenda_nova"),
    path("encomendas/<int:pk>/", views.OrderDetailView.as_view(), name="encomenda"),
    path("encomendas/<int:pk>/imprimir/", views.OrderPrintView.as_view(), name="encomenda_imprimir"),
    path("encomendas/<int:pk>/receber/", views.ReceiveView.as_view(), name="receber"),
    path("rececoes/", views.ReceiptListView.as_view(), name="rececoes"),
    path("rececoes/nova/", views.ReceiveView.as_view(), name="rececao_nova"),
    path("rececoes/<int:pk>/", views.ReceiptDetailView.as_view(), name="rececao"),
    path("fornecedores/", views.SupplierListView.as_view(), name="fornecedores"),
    path("fornecedores/novo/", views.SupplierFormView.as_view(), name="fornecedor_novo"),
    path("fornecedores/<int:pk>/", views.SupplierDetailView.as_view(), name="fornecedor"),
    path("fornecedores/<int:pk>/editar/", views.SupplierFormView.as_view(), name="fornecedor_editar"),
    path("artigo/<int:pk>/precos/", views.ItemPricesView.as_view(), name="precos"),
]
