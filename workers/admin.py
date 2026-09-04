from django.contrib import admin

from .models import Worker


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "job_title", "contact", "is_active", "user")
    list_filter = ("is_active",)
    search_fields = ("full_name",)
