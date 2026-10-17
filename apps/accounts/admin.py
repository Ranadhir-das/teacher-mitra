from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .forms import AdminUserCreationForm, AdminUserChangeForm
from .models import User, Team, CounsellorHistory
from .counsellor_permissions import visible_counsellors, can_manage_counsellors


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = AdminUserCreationForm
    form = AdminUserChangeForm
    list_display = ("email", "username", "name", "role", "account_status", "is_active", "is_staff", "date_joined")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("name", "email", "phone", "username", "employee_id")
    ordering = ("name",)
    readonly_fields = ("last_login", "date_joined")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("name", "phone", "profile_photo", "role")}),
        ("Employment", {"fields": ("username", "employee_id", "joining_date", "account_status", "profile_information")}),
        ("Access", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "name", "role", "password1", "password2")}),)

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    has_add_permission = has_view_permission
    has_change_permission = has_view_permission
    has_delete_permission = has_view_permission

admin.site.site_header = "Aspiring Life Partners"
admin.site.site_title = "ALP Administration"
admin.site.index_title = "Platform administration"


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "leader", "is_active")
    search_fields = ("name", "leader__name")
    list_filter = ("is_active",)
    filter_horizontal = ("members",)
    list_select_related = ("leader",)

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    has_add_permission = has_view_permission
    has_change_permission = has_view_permission

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CounsellorHistory)
class CounsellorHistoryAdmin(admin.ModelAdmin):
    list_display = ("counsellor", "actor", "action", "created_at")
    readonly_fields = ("counsellor", "actor", "action", "changes", "created_at")

    def get_queryset(self, request):
        return super().get_queryset(request).filter(counsellor__in=visible_counsellors(request.user)).select_related("actor", "counsellor")

    def has_module_permission(self, request):
        return can_manage_counsellors(request.user)

    def has_view_permission(self, request, obj=None):
        return can_manage_counsellors(request.user) and (obj is None or visible_counsellors(request.user).filter(pk=obj.counsellor_id).exists())

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
