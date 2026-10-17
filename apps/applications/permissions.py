from apps.accounts.permissions import is_internal_user, can_manage_employees
from apps.leads.models import Lead
from apps.leads.permissions import visible_leads
from .models import Application


def application_leads(user):
    if not is_internal_user(user):
        return Lead.objects.none()
    # Application-wide oversight is explicitly granted to team leaders.
    if can_manage_employees(user) or user.role == "TEAM_LEADER":
        return Lead.objects.all()
    return visible_leads(user)


def visible_applications(user):
    return Application.objects.filter(lead__in=application_leads(user))
