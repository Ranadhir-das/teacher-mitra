from rest_framework.permissions import BasePermission
from ..permissions import can_manage_employees


class CanManageEmployees(BasePermission):
    def has_permission(self, request, view):
        return can_manage_employees(request.user)
