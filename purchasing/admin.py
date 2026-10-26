from django.contrib import admin

from .models import PurchaseOrder, PurchaseOrderLine, Receipt, ReceiptLine, Supplier, SupplierItem


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "nif", "organization", "is_active")
    list_filter = ("organization", "is_active")
    search_fields = ("name", "nif")


@admin.register(SupplierItem)
class SupplierItemAdmin(admin.ModelAdmin):
    list_display = ("item", "supplier", "supplier_ref", "last_price", "preferred")
    list_filter = ("supplier",)


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 0


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ("__str__", "restaurant", "supplier", "state", "created_at")
    list_filter = ("restaurant", "state")
    inlines = [PurchaseOrderLineInline]


class ReceiptLineInline(admin.TabularInline):
    model = ReceiptLine
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    """Consulta apenas: uma receção mexeu no stock e não se apaga
    (invariante 2). Um erro corrige-se com um ajuste."""

    list_display = ("__str__", "restaurant", "supplier", "document_number", "document_date", "received_by")
    list_filter = ("restaurant", "supplier")
    inlines = [ReceiptLineInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
