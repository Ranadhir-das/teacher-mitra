"""All CRM mutations share authorization, transactions and audit writes here."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.utils import timezone
from apps.accounts.models import User
from .models import Lead, LeadAssignment, LeadStatusHistory, LeadNote
from .permissions import manageable_leads, visible_leads, is_admin, can_create, can_assign, can_archive, permitted_teams
from .workflow import allowed_statuses

EDITABLE_FIELDS = (
    "full_name", "phone", "alternate_phone", "email", "date_of_birth", "gender", "address", "city", "state", "pincode",
    "highest_qualification", "institution_name", "passing_year", "percentage_or_cgpa", "specialization",
    "selected_country", "selected_university", "selected_course", "desired_course", "desired_specialization", "preferred_university", "preferred_study_mode", "budget", "career_goal",
    "additional_requirements", "lead_source", "priority", "general_notes", "partner",
)


class DuplicateLeadError(ValidationError):
    def __init__(self, matches):
        self.matches = matches
        super().__init__("Possible duplicate lead found. Review the warning and confirm to continue.")


def duplicates(lead):
    phones = [phone for phone in (lead.phone, lead.alternate_phone) if phone]
    match = Q(phone__in=phones) | Q(alternate_phone__in=phones)
    if lead.email:
        match |= Q(email__iexact=lead.email)
    return Lead.objects.filter(match).exclude(pk=lead.pk)


def duplicate_summary(actor, matches):
    # Never disclose a private lead's contact details/name to another counsellor/team.
    result = list(visible_leads(actor).filter(pk__in=matches.values("pk")).select_related("assigned_counsellor").values(
        "id", "full_name", "phone", "status", "assigned_counsellor__name")[:10])
    for row in result:
        row["status_display"] = dict(Lead.Status.choices)[row["status"]]
    return result


def locked_lead(actor, pk, active=True):
    try:
        lead = manageable_leads(actor).select_for_update().get(pk=pk)
    except Lead.DoesNotExist:
        raise Http404("Lead not found.")
    if active and not lead.is_active:
        raise ValidationError("Archived leads are read-only. Restore the lead first.")
    return lead


def validate_assignment(actor, counsellor, team, lead=None):
    if not can_assign(actor):
        raise PermissionDenied("You cannot assign leads.")
    if team and not team.is_active:
        raise ValidationError("Choose an active team.")
    if counsellor and (not counsellor.is_active or counsellor.role != User.Role.COUNSELLOR):
        raise ValidationError("Choose an active counsellor.")
    if team and counsellor and not team.members.filter(pk=counsellor.pk).exists():
        raise ValidationError("The counsellor must belong to the selected team.")
    if not is_admin(actor):
        if actor.role == User.Role.TEAM_LEADER:
            if not team or not permitted_teams(actor).filter(pk=team.pk).exists():
                raise PermissionDenied("Assignment must remain within your permitted teams.")
        elif not lead or not team or team.pk != lead.assigned_team_id or not actor.crm_teams.filter(pk=team.pk).exists():
            raise PermissionDenied("Delegated reassignment must remain in the lead's existing team.")


def save_checked(lead):
    lead.full_clean()
    lead.save()


def record_status(lead, actor, value, note=""):
    if value == lead.status:
        return
    if value not in dict(allowed_statuses(actor, lead)):
        raise ValidationError({"status": "This status transition is not permitted."})
    if value == Lead.Status.ASSIGNED and not lead.assigned_counsellor_id:
        raise ValidationError({"status": "Assign a counsellor before using Assigned status."})
    previous = lead.status
    lead.status = value
    lead.updated_by = actor
    if value == Lead.Status.CONTACTED:
        lead.last_contacted_at = timezone.now()
    save_checked(lead)
    LeadStatusHistory.objects.create(lead=lead, previous_status=previous, new_status=value, changed_by=actor, note=note)


def record_assignment(lead, actor, counsellor, team, reason):
    if (lead.assigned_counsellor_id, lead.assigned_team_id) == (getattr(counsellor, "pk", None), getattr(team, "pk", None)):
        return
    LeadAssignment.objects.create(lead=lead, previous_counsellor=lead.assigned_counsellor,
        new_counsellor=counsellor, previous_team=lead.assigned_team, new_team=team, assigned_by=actor, reason=reason)
    lead.assigned_counsellor = counsellor
    lead.assigned_team = team
    lead.updated_by = actor
    save_checked(lead)
    if counsellor and lead.status == Lead.Status.NEW:
        record_status(lead, actor, Lead.Status.ASSIGNED, "Counsellor assigned.")
    elif not counsellor and lead.status == Lead.Status.ASSIGNED:
        # Assignment removal is a structural reset, recorded even for team leaders.
        lead.status = Lead.Status.NEW
        save_checked(lead)
        LeadStatusHistory.objects.create(lead=lead, previous_status=Lead.Status.ASSIGNED,
            new_status=Lead.Status.NEW, changed_by=actor, note="Counsellor unassigned.")


@transaction.atomic
def create_lead(actor, data, *, counsellor=None, team=None, tags=(), confirm_duplicate=False):
    if not can_create(actor):
        raise PermissionDenied("Only administrators and configured team leaders can create leads.")
    if not is_admin(actor) or counsellor or team:
        validate_assignment(actor, counsellor, team)
    if set(data) - set(EDITABLE_FIELDS):
        raise ValidationError("Unsupported lead fields.")
    if "partner" in data and not is_admin(actor):
        raise PermissionDenied("Only administrators can set partner attribution.")
    lead = Lead(**data, created_by=actor, updated_by=actor)
    lead.full_clean()
    matches = duplicates(lead)
    if matches.exists() and not confirm_duplicate:
        raise DuplicateLeadError(duplicate_summary(actor, matches))
    lead.save()
    lead.tags.set(tags)
    LeadStatusHistory.objects.create(lead=lead, previous_status="", new_status=Lead.Status.NEW, changed_by=actor, note="Lead created.")
    record_assignment(lead, actor, counsellor, team, "Initial assignment.")
    return lead


@transaction.atomic
def update_lead(actor, pk, data, *, tags=None, confirm_duplicate=False):
    lead = locked_lead(actor, pk)
    if set(data) - set(EDITABLE_FIELDS):
        raise ValidationError("Use the dedicated assignment, status or archive action.")
    if "partner" in data and not is_admin(actor):
        raise PermissionDenied("Only administrators can change partner attribution.")
    old_selection = (lead.selected_country_id, lead.selected_university_id, lead.selected_course_id)
    if "selected_university" in data and "selected_country" not in data:
        data = {**data, "selected_country": data["selected_university"].country if data["selected_university"] else None}
    old_contacts = (lead.phone, lead.alternate_phone, lead.email)
    for field, value in data.items():
        setattr(lead, field, value)
    lead.full_clean()
    matches = duplicates(lead)
    if old_contacts != (lead.phone, lead.alternate_phone, lead.email) and matches.exists():
        if not confirm_duplicate or not can_create(actor):
            raise DuplicateLeadError(duplicate_summary(actor, matches))
    lead.updated_by = actor
    lead.save()
    if old_selection != (lead.selected_country_id, lead.selected_university_id, lead.selected_course_id):
        LeadNote.objects.create(lead=lead, created_by=actor,
            note=f"Counselling selection updated: Country: {lead.selected_country or 'Not selected'}; University: {lead.selected_university or 'Not selected'}; Course: {lead.selected_course or 'Not selected'}.")
    if tags is not None:
        lead.tags.set(tags)
    return lead


@transaction.atomic
def assign_lead(actor, pk, counsellor, team, reason=""):
    lead = locked_lead(actor, pk)
    validate_assignment(actor, counsellor, team, lead)
    record_assignment(lead, actor, counsellor, team, reason)
    return lead


@transaction.atomic
def change_status(actor, pk, status, note=""):
    lead = locked_lead(actor, pk)
    record_status(lead, actor, status, note)
    return lead


@transaction.atomic
def add_note(actor, pk, note):
    lead = locked_lead(actor, pk)
    entry = LeadNote(lead=lead, note=note.strip(), created_by=actor)
    entry.full_clean()
    entry.save()
    lead.updated_by = actor
    lead.save(update_fields=["updated_by", "updated_at"])
    return entry


@transaction.atomic
def archive_lead(actor, pk, *, active=False):
    if not can_archive(actor):
        raise PermissionDenied("You cannot archive or restore leads.")
    lead = locked_lead(actor, pk, active=False)
    if lead.is_active != active:
        lead.is_active = active
        lead.updated_by = actor
        lead.save(update_fields=["is_active", "updated_by", "updated_at"])
        LeadNote.objects.create(lead=lead, note="Lead restored." if active else "Lead archived.", created_by=actor)
    return lead


@transaction.atomic
def bulk_update(actor, ids, operation, **kwargs):
    ids = sorted(set(ids))
    if not ids or len(ids) > 100:
        raise ValidationError("Select between 1 and 100 leads.")
    # Lock in a stable order and reject the entire batch if any record is inaccessible.
    leads = list(manageable_leads(actor).select_for_update().filter(pk__in=ids).order_by("pk"))
    if len(leads) != len(ids):
        raise PermissionDenied("One or more selected leads are unavailable.")
    for lead in leads:
        if operation == "assign":
            assign_lead(actor, lead.pk, **kwargs)
        elif operation == "status":
            change_status(actor, lead.pk, **kwargs)
        else:
            raise ValidationError("Unsupported bulk action.")
    return len(leads)
