from rest_framework.permissions import BasePermission
from ..permissions import can_create
from apps.accounts.permissions import is_internal_user


class LeadAccessPermission(BasePermission):
    def has_permission(self, request, view):
        if not is_internal_user(request.user):
            return False
        return view.action != "create" or can_create(request.user)


class InternalUserPermission(BasePermission):
    def has_permission(self, request, view):
        return is_internal_user(request.user)
