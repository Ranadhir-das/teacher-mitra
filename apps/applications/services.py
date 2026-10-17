"""Authorized, atomic application writes for both CRM and Django admin."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from apps.leads.models import Lead, LeadStatusHistory
from .models import Application, ApplicationStatusHistory
from .permissions import application_leads

EDITABLE_FIELDS = ("university", "course", "reference", "status", "submission_date", "academic_details", "remarks")
TRANSITIONS = {
    "DRAFT": {"STARTED", "CANCELLED"},
    "STARTED": {"SUBMITTED", "CANCELLED"},
    "SUBMITTED": {"UNDER_REVIEW", "APPROVED", "REJECTED", "CANCELLED"},
    "UNDER_REVIEW": {"APPROVED", "REJECTED", "CANCELLED"},
    "APPROVED": set(), "REJECTED": set(), "CANCELLED": set(),
}


def validate_workflow(application, old=None):
    if not application.lead.is_active:
        raise ValidationError("Archived leads are read-only. Restore the lead first.")
    if old is None:
        if application.status not in ("DRAFT", "STARTED"):
            raise ValidationError({"status": "New applications must be Draft or Started."})
    elif application.status != old.status and application.status not in TRANSITIONS[old.status]:
        raise ValidationError({"status": "This status transition is not permitted."})
    if old and hasattr(old, "admission") and application.status in ("REJECTED", "CANCELLED") and old.admission.status != "CANCELLED":
        raise ValidationError("Cancel the admission before rejecting or cancelling the application.")


def snapshot(application):
    return {field: str(getattr(application, field) or "") for field in EDITABLE_FIELDS}


def sync_lead(lead, actor, application):
    targets = {"STARTED": "APPLICATION_STARTED", "SUBMITTED": "APPLICATION_SUBMITTED",
               "UNDER_REVIEW": "APPLICATION_SUBMITTED", "APPROVED": "APPLICATION_SUBMITTED"}
    target = targets.get(application.status)
    ranks = {"APPLICATION_STARTED": 1, "APPLICATION_SUBMITTED": 2, "PAYMENT_PENDING": 3, "ADMISSION_CONFIRMED": 4}
    if not target or ranks.get(lead.status, 0) >= ranks[target]:
        return
    previous = lead.status
    lead.status = target
    lead.updated_by = actor
    lead.save(update_fields=["status", "updated_by", "updated_at"])
    LeadStatusHistory.objects.create(lead=lead, previous_status=previous, new_status=target,
        changed_by=actor, note=f"Application #{application.pk}: {application.get_status_display()}.")


@transaction.atomic
def save_application(actor, data, *, lead_id=None, pk=None):
    if set(data) - set(EDITABLE_FIELDS):
        raise ValidationError("Unsupported application fields.")
    if pk:
        # Lock the lead first: sibling applications serialize their lead updates.
        lead_id = get_object_or_404(Application, pk=pk).lead_id
    lead = get_object_or_404(application_leads(actor).select_for_update(), pk=lead_id)
    old = get_object_or_404(Application.objects.select_for_update(), pk=pk, lead=lead) if pk else None
    application = get_object_or_404(Application, pk=pk) if pk else Application(lead=lead, created_by=actor)
    before = snapshot(old) if old else {}
    for field, value in data.items():
        setattr(application, field, value)
    application.updated_by = actor
    validate_workflow(application, old)
    if application.status in ("SUBMITTED", "UNDER_REVIEW", "APPROVED", "REJECTED") and not application.submission_date:
        application.submission_date = old.submission_date if old and old.submission_date else timezone.localdate()
    if old and old.submission_date and not application.submission_date:
        application.submission_date = old.submission_date
    application.full_clean()
    after = snapshot(application)
    changes = {key: {"before": before.get(key, ""), "after": value} for key, value in after.items() if before.get(key) != value}
    if not old or changes:
        application.save()
        ApplicationStatusHistory.objects.create(application=application, previous_status=old.status if old else "",
            new_status=application.status, changed_by=actor, changes=changes)
        if not old or old.status != application.status:
            sync_lead(lead, actor, application)
    return application
