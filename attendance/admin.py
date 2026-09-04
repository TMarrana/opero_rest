from django.contrib import admin

from .models import TimeEntry


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    """Consulta e correção auditada fazem-se na aplicação; o admin não
    apaga registos de ponto."""

    list_display = ("worker", "check_in", "check_out", "corrected_by")
    date_hierarchy = "check_in"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
