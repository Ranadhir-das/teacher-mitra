from django.contrib import admin
from apps.accounts.permissions import can_manage_employees, is_internal_user
from .models import Country, University


class CatalogueAdmin(admin.ModelAdmin):
    list_filter = ("is_active",)
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")

    def has_module_permission(self, request):
        return is_internal_user(request.user)

    def has_view_permission(self, request, obj=None):
        return is_internal_user(request.user)

    def has_change_permission(self, request, obj=None):
        return can_manage_employees(request.user)

    has_add_permission = has_change_permission

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(University)
class UniversityAdmin(CatalogueAdmin):
    from .forms import UniversityForm
    form = UniversityForm
    list_display = ("name", "country", "is_active", "created_at")
    list_filter = ("country", "is_active")
    search_fields = ("name", "country__name", "country__code")
    list_select_related = ("country",)


@admin.register(Country)
class CountryAdmin(CatalogueAdmin):
    list_display = ("name", "code", "is_active", "created_at")
    search_fields = ("name", "code")
