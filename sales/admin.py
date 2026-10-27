from django.contrib import admin

from .models import PosProduct, SaleStockMovement, SalesDocument, SalesImport, SalesSettings


@admin.register(SalesSettings)
class SalesSettingsAdmin(admin.ModelAdmin):
    list_display = ("restaurant", "day_cutoff_hour", "service_change_hour", "series", "hourly_cost")


@admin.register(SalesImport)
class SalesImportAdmin(admin.ModelAdmin):
    """Consulta apenas: uma importação só se cria pelo ecrã Vendas → Importar."""

    list_display = ("restaurant", "period_start", "period_end", "documents_new", "documents_updated", "imported_by", "created_at")
    list_filter = ("restaurant",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PosProduct)
class PosProductAdmin(admin.ModelAdmin):
    list_display = ("description", "code", "group", "last_price", "restaurant")
    list_filter = ("restaurant", "group")
    search_fields = ("description", "code")


@admin.register(SalesDocument)
class SalesDocumentAdmin(admin.ModelAdmin):
    """Consulta apenas: os documentos vêm do SAF-T e não se editam."""

    list_display = ("number", "doc_type", "status", "system_entry", "service_date", "net_total", "restaurant")
    list_filter = ("restaurant", "doc_type", "status")
    search_fields = ("number",)
    date_hierarchy = "service_date"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SaleStockMovement)
class SaleStockMovementAdmin(admin.ModelAdmin):
    """Consulta apenas (Fase 14): cada linha tem o seu movimento, que não se apaga."""

    list_display = ("service_date", "restaurant", "item", "quantity", "sales_import")
    list_filter = ("restaurant",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
