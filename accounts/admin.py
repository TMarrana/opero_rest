from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Membership, User


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "role", "restaurant", "is_group_admin", "is_active")
    inlines = [MembershipInline]
    list_filter = ("role", "is_active")
    search_fields = ("email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Informação pessoal", {"fields": ("first_name", "last_name")}),
        ("Opero", {"fields": ("organization", "is_group_admin", "restaurant", "role")}),
        ("Permissões", {"fields": ("is_active", "is_staff", "is_superuser", "groups")}),
        ("Datas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2", "restaurant", "role")}),
    )
