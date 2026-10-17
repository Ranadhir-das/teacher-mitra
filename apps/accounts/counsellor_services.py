from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from .models import User, CounsellorHistory, Team
from .permissions import can_manage_employees
from .counsellor_permissions import can_manage_counsellors, can_edit_counsellor, visible_counsellors, counsellor_teams
from apps.leads.validators import normalize_phone

FIELDS = ("name", "email", "phone", "employee_id", "username", "joining_date", "account_status", "profile_information")


def snapshot(user):
    return {field: str(getattr(user, field) or "") for field in FIELDS}


def locked_counsellor(actor, pk):
    target = get_object_or_404(User.objects.select_for_update().filter(pk__in=visible_counsellors(actor).values("pk")), pk=pk)
    if not can_edit_counsellor(actor, target):
        raise PermissionDenied("This counsellor requires administrator management.")
    return target


@transaction.atomic
def save_counsellor(actor, data, *, teams=None, password=None, pk=None):
    if not can_manage_counsellors(actor):
        raise PermissionDenied
    if set(data) - set(FIELDS):
        raise ValidationError("Unsupported counsellor fields.")
    target = locked_counsellor(actor, pk) if pk else User(role=User.Role.COUNSELLOR)
    if pk and password is not None:
        raise ValidationError("Use the password reset action.")
    before = snapshot(target) if pk else {}
    previous_teams = list(target.crm_teams.order_by("pk").values_list("pk", flat=True)) if pk else []
    for field, value in data.items():
        setattr(target, field, value)
    target.name = target.name.strip()
    if not target.name or not (target.username or "").strip() or not (target.employee_id or "").strip():
        raise ValidationError("Name, username and employee ID are required.")
    target.phone = normalize_phone(target.phone)
    target.is_active = target.account_status == User.Status.ACTIVE
    if not pk:
        if not password:
            raise ValidationError("A password is required.")
        validate_password(password, user=target)
        target.set_password(password)
    target.full_clean()
    if teams is not None:
        ids = sorted({team.pk for team in teams})
        allowed = counsellor_teams(actor)
        # Retain existing inactive teams for admins without permitting new inactive assignments.
        if can_manage_employees(actor):
            allowed = Team.objects.filter(pk__in=list(allowed.values_list("pk", flat=True)) + previous_teams)
        selected = list(allowed.select_for_update().filter(pk__in=ids))
        if len(selected) != len(ids) or (not can_manage_employees(actor) and not ids):
            raise ValidationError("Select active teams you manage; team leaders must select a team.")
    elif not pk and not can_manage_employees(actor):
        raise ValidationError("A team is required.")
    target.save()
    if teams is not None:
        target.crm_teams.set(selected)
    after = snapshot(target)
    changes = {field: {"before": before.get(field, ""), "after": value} for field, value in after.items() if before.get(field) != value}
    current_teams = list(target.crm_teams.order_by("pk").values_list("pk", flat=True))
    if previous_teams != current_teams:
        changes["teams"] = {"before": previous_teams, "after": current_teams}
    if not pk or changes:
        CounsellorHistory.objects.create(counsellor=target, actor=actor, action="UPDATED" if pk else "CREATED", changes=changes)
    return target


@transaction.atomic
def reset_counsellor_password(actor, pk, password):
    target = locked_counsellor(actor, pk)
    # Team leaders manage their team profile/status, but password takeover is administrator-only.
    if not can_manage_employees(actor):
        raise PermissionDenied("Only administrators can reset passwords.")
    validate_password(password, user=target)
    target.set_password(password)
    target.save(update_fields=["password"])
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
    for token in OutstandingToken.objects.filter(user=target):
        BlacklistedToken.objects.get_or_create(token=token)
    CounsellorHistory.objects.create(counsellor=target, actor=actor, action="PASSWORD_RESET")
    return target
