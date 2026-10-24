from django.contrib import admin

from .models import Restaurant, WorkArea


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(WorkArea)
class WorkAreaAdmin(admin.ModelAdmin):
    """Áreas arquivam-se (archived_at) em vez de se apagarem: as
    marcações já feitas apontam para elas."""

    list_display = ("name", "restaurant", "archived_at")
    list_filter = ("restaurant",)

    def has_delete_permission(self, request, obj=None):
        return False
