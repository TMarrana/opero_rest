from django.contrib import admin

from .models import BreakType, EntryCorrection, TimeEntry


class _SoConsulta(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TimeEntry)
class TimeEntryAdmin(_SoConsulta):
    """Consulta e correção auditada fazem-se na aplicação; o admin não
    apaga registos de ponto."""

    list_display = ("worker", "work_date", "check_in", "check_out", "work_area", "source", "corrected_by")
    date_hierarchy = "check_in"


@admin.register(EntryCorrection)
class EntryCorrectionAdmin(_SoConsulta):
    """Histórico de correções (invariante 7): só consulta."""

    list_display = ("entry", "kind", "corrected_by", "corrected_at", "reason")


@admin.register(BreakType)
class BreakTypeAdmin(admin.ModelAdmin):
    """Tipos de pausa arquivam-se (archived_at) em vez de se apagarem:
    as pausas já registadas apontam para eles (R-006)."""

    list_display = ("name", "paid", "restaurant", "archived_at")
    list_filter = ("restaurant",)

    def has_delete_permission(self, request, obj=None):
        return False
