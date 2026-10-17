from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


def can_manage_employees(user):
    return bool(is_internal_user(user) and (user.is_superuser or user.role in ("SUPER_ADMIN", "ADMIN")))


def is_internal_user(user):
    return bool(user.is_authenticated and user.is_active and user.role in ("SUPER_ADMIN", "ADMIN", "TEAM_LEADER", "COUNSELLOR"))


def is_super_admin(user):
    return bool(user.is_authenticated and user.is_active and (user.is_superuser or user.role == "SUPER_ADMIN"))


def can_edit_employee(actor, employee):
    if not can_manage_employees(actor) or employee.role == "PARTNER":
        return False
    return is_super_admin(actor) or (not employee.is_superuser and not employee.is_staff and employee.role != "SUPER_ADMIN")


class EmployeeManagementMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        from .counsellor_permissions import can_manage_counsellors
        return can_manage_counsellors(self.request.user)
