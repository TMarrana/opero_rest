from django.contrib import admin

from .models import Recipe, RecipeLine, RecipeProduct, RecipeVersion


class RecipeLineInline(admin.TabularInline):
    model = RecipeLine
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "organization", "sale_price", "is_active")
    list_filter = ("organization", "kind", "is_active")
    search_fields = ("name",)


@admin.register(RecipeVersion)
class RecipeVersionAdmin(admin.ModelAdmin):
    """Consulta apenas: uma versão não muda depois de criada; uma alteração
    é uma versão nova, feita no ecrã das fichas."""

    list_display = ("__str__", "valid_from", "portions", "created_by", "created_at")
    list_filter = ("recipe__organization",)
    inlines = [RecipeLineInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(RecipeProduct)
class RecipeProductAdmin(admin.ModelAdmin):
    list_display = ("recipe", "product", "created_by", "created_at")
    list_filter = ("product__restaurant",)
