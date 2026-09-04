from django.contrib import admin

from .models import VacationRequest


@admin.register(VacationRequest)
class VacationRequestAdmin(admin.ModelAdmin):
    """Invariante 6: pedidos aprovados não se apagam — nem no admin."""

    list_display = ("worker", "start_date", "end_date", "status", "decided_by")
    list_filter = ("status",)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.status == VacationRequest.Status.APROVADO:
            return False
        return super().has_delete_permission(request, obj)
