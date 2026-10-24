from django.contrib import admin

from .models import RestDay, Shift, ShiftTemplate, WeekPublication


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ("worker", "work_date", "start_at", "end_at", "state", "pending_removal")
    list_filter = ("state",)


admin.site.register(ShiftTemplate)
admin.site.register(RestDay)
admin.site.register(WeekPublication)
