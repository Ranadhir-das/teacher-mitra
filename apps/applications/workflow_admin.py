from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from apps.accounts.permissions import is_internal_user


class WorkflowAdmin(admin.ModelAdmin):
    """Scoped admin inspection with service-backed workflow screens for writes."""
    create_url = None

    def get_queryset(self, request):
        return super().get_queryset(request).filter(pk__in=self.scope(request.user).values("pk"))

    def has_module_permission(self, request):
        return is_internal_user(request.user)

    def has_view_permission(self, request, obj=None):
        return is_internal_user(request.user) and (obj is None or self.scope(request.user).filter(pk=obj.pk).exists())

    def has_add_permission(self, request):
        return bool(self.create_url and is_internal_user(request.user))

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields if field.name != "file"]

    def add_view(self, request, form_url="", extra_context=None):
        if not self.has_add_permission(request):
            raise PermissionDenied
        return redirect(self.create_url)
