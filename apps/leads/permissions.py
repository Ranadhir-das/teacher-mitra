from apps.accounts.models import Team, User
from apps.accounts.permissions import can_manage_employees
from .models import Lead
from django.db.models import Q


def is_admin(user):
    return can_manage_employees(user)


def permitted_teams(user):
    teams = Team.objects.filter(is_active=True)
    return teams if is_admin(user) else teams.filter(leader=user)


def visible_leads(user):
    queryset = Lead.objects.all()
    if not user.is_authenticated or not user.is_active:
        return queryset.none()
    if is_admin(user):
        return queryset
    if user.role == User.Role.TEAM_LEADER:
        return queryset.filter(Q(assigned_team__in=permitted_teams(user)) | Q(partner__isnull=False, lead_source=Lead.Source.PARTNER))
    if user.role == User.Role.COUNSELLOR:
        return queryset.filter(assigned_counsellor=user)
    return queryset.none()


def can_create(user):
    return is_admin(user) or (user.is_authenticated and user.is_active and user.role == User.Role.TEAM_LEADER and permitted_teams(user).exists())


def can_assign(user):
    return is_admin(user) or (user.is_authenticated and user.is_active and (user.role == User.Role.TEAM_LEADER or user.has_perm("leads.reassign_lead")))


def can_archive(user):
    return is_admin(user) or (user.is_authenticated and user.is_active and user.has_perm("leads.archive_lead"))


def assignment_choices(user):
    users = User.objects.filter(is_active=True, role=User.Role.COUNSELLOR)
    if not is_admin(user):
        teams = permitted_teams(user) if user.role == User.Role.TEAM_LEADER else user.crm_teams.filter(is_active=True)
        users = users.filter(crm_teams__in=teams).distinct()
    return users


def optimized(queryset):
    return queryset.select_related("assigned_counsellor", "assigned_team", "created_by", "updated_by", "partner", "selected_country", "selected_university__country", "selected_course__university__country").prefetch_related("tags")


def manageable_leads(user):
    """Review visibility does not grant cross-team mutation rights."""
    queryset = visible_leads(user)
    if getattr(user, "role", None) == User.Role.TEAM_LEADER and not is_admin(user):
        queryset = queryset.filter(assigned_team__in=permitted_teams(user))
    return queryset
