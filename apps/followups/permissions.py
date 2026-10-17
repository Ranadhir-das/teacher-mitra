from rest_framework.permissions import BasePermission
from apps.accounts.permissions import is_internal_user, can_manage_employees
from apps.accounts.models import User
from apps.leads.permissions import manageable_leads
from .models import FollowUp


def visible_followups(user):
    return FollowUp.objects.filter(lead__in=manageable_leads(user))


def assignee_choices(user, lead):
    users = User.objects.filter(is_active=True).exclude(role="PARTNER")
    if can_manage_employees(user):
        return users
    if user.role == "TEAM_LEADER":
        return users.filter(pk__in=[user.pk, lead.assigned_counsellor_id])
    return users.filter(pk=user.pk)


class FollowUpPermission(BasePermission):
    def has_permission(self, request, view):
        return is_internal_user(request.user)

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view) and visible_followups(request.user).filter(pk=obj.pk).exists()
