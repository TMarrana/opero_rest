from django.contrib import admin

from .models import AbsenceType, Allowance, BlockedPeriod, Holiday, VacationRequest


@admin.register(VacationRequest)
class VacationRequestAdmin(admin.ModelAdmin):
    """Invariante 6: pedidos aprovados não se apagam — nem no admin."""

    list_display = ("worker", "absence_type", "start_date", "end_date", "days_taken", "status", "decided_by")
    list_filter = ("status", "absence_type")

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.status == VacationRequest.Status.APROVADO:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(AbsenceType)
class AbsenceTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "restaurant", "deducts_balance", "requires_approval", "half_days", "archived_at")

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Allowance)
admin.site.register(Holiday)
admin.site.register(BlockedPeriod)
