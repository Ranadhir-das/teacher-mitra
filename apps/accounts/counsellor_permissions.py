from .models import User, Team
from .permissions import can_manage_employees, can_edit_employee, is_internal_user


def can_manage_counsellors(actor):
    return can_manage_employees(actor) or (is_internal_user(actor) and actor.role == User.Role.TEAM_LEADER)


def counsellor_teams(actor):
    teams = Team.objects.filter(is_active=True)
    if can_manage_employees(actor):
        return teams
    if can_manage_counsellors(actor):
        return teams.filter(leader=actor)
    return teams.none()


def visible_counsellors(actor):
    users = User.objects.filter(role=User.Role.COUNSELLOR)
    if can_manage_employees(actor):
        return users
    if can_manage_counsellors(actor):
        return users.filter(crm_teams__in=counsellor_teams(actor)).distinct()
    return users.none()


def can_edit_counsellor(actor, target):
    if target.role != User.Role.COUNSELLOR:
        return False
    if can_manage_employees(actor):
        return can_edit_employee(actor, target)
    return bool(can_manage_counsellors(actor) and not target.is_staff and not target.is_superuser
        and target.crm_teams.filter(pk__in=counsellor_teams(actor)).exists()
        and not target.crm_teams.exclude(pk__in=counsellor_teams(actor)).exists())
