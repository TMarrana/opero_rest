from django.contrib import admin

from .models import Category, Item, StockMovement


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "restaurant")
    list_filter = ("restaurant",)


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "unit", "current_stock", "minimum_stock", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name",)
    # Invariante 1: nem o admin escreve o stock diretamente.
    readonly_fields = ("current_stock",)


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    """Consulta apenas (invariantes 1 e 2): movimentos criam-se só via
    inventory.services.register_movement e nunca se alteram nem apagam."""

    list_display = ("occurred_at", "item", "movement_type", "quantity", "created_by")
    list_filter = ("movement_type",)
    date_hierarchy = "occurred_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
