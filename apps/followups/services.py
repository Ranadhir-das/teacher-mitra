from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone

from .models import FollowUp


def locked_followup(followup, actor):
    from apps.leads.services import locked_lead
    from .permissions import visible_followups
    from django.shortcuts import get_object_or_404
    locked_lead(actor, followup.lead_id)
    return get_object_or_404(visible_followups(actor).select_for_update(), pk=followup.pk)



@transaction.atomic
def create_followup(
    *,
    lead,
    assigned_to,
    created_by,
    followup_type,
    scheduled_at,
    notes="",
):
    from apps.leads.services import locked_lead
    from .permissions import assignee_choices
    lead = locked_lead(created_by, lead.pk)
    if not assignee_choices(created_by, lead).filter(pk=assigned_to.pk).exists():
        raise PermissionDenied("Choose an accessible follow-up owner.")
    if scheduled_at < timezone.now():
        raise ValidationError(
            "Follow-up time cannot be in the past."
        )

    followup = FollowUp(
        lead=lead,
        assigned_to=assigned_to,
        created_by=created_by,
        followup_type=followup_type,
        scheduled_at=scheduled_at,
        notes=notes,
        status=FollowUp.Status.SCHEDULED,
    )

    followup.full_clean()
    followup.save()

    return followup


@transaction.atomic
def complete_followup(
    *,
    followup,
    actor,
    outcome="",
    notes="",
):
    followup = locked_followup(followup, actor)
    if followup.status == FollowUp.Status.COMPLETED:
        raise ValidationError(
            "This follow-up is already completed."
        )

    if followup.status == FollowUp.Status.CANCELLED:
        raise ValidationError(
            "A cancelled follow-up cannot be completed."
        )

    followup.status = FollowUp.Status.COMPLETED
    followup.outcome = outcome
    followup.notes = notes
    followup.completed_at = timezone.now()

    followup.full_clean()
    followup.save(
        update_fields=[
            "status",
            "outcome",
            "notes",
            "completed_at",
            "updated_at",
        ]
    )

    return followup


@transaction.atomic
def mark_followup_missed(*, followup, actor):
    followup = locked_followup(followup, actor)
    if followup.status == FollowUp.Status.COMPLETED:
        raise ValidationError(
            "A completed follow-up cannot be marked as missed."
        )

    if followup.status == FollowUp.Status.CANCELLED:
        raise ValidationError(
            "A cancelled follow-up cannot be marked as missed."
        )

    followup.status = FollowUp.Status.MISSED
    followup.completed_at = None

    followup.full_clean()
    followup.save(
        update_fields=[
            "status",
            "completed_at",
            "updated_at",
        ]
    )

    return followup


@transaction.atomic
def cancel_followup(*, followup, actor):
    followup = locked_followup(followup, actor)
    if followup.status == FollowUp.Status.COMPLETED:
        raise ValidationError(
            "A completed follow-up cannot be cancelled."
        )

    if followup.status == FollowUp.Status.CANCELLED:
        raise ValidationError(
            "This follow-up is already cancelled."
        )

    followup.status = FollowUp.Status.CANCELLED
    followup.completed_at = None

    followup.full_clean()
    followup.save(
        update_fields=[
            "status",
            "completed_at",
            "updated_at",
        ]
    )

    return followup
