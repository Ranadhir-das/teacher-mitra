from django.utils import timezone
from django.urls import reverse
from django.db.models import Q

from apps.leads.permissions import visible_leads
from apps.leads.models import LeadStatusHistory, LeadNote
from apps.applications.models import ApplicationStatusHistory, Admission
from apps.applications.permissions import visible_applications
from apps.followups.permissions import visible_followups


def counsellor_workload(actor, counsellor, start_date=None, end_date=None):
    """Build counsellor workload and performance metrics."""

    leads = visible_leads(actor).filter(
        assigned_counsellor=counsellor,
        is_active=True,
    )

    applications = visible_applications(actor).filter(
        lead__in=leads
    )

    followups = visible_followups(actor).filter(
        assigned_to=counsellor,
        lead__in=leads,
    )

    # Apply optional date range to activity-based metrics.
    if start_date:
        applications = applications.filter(
            created_at__date__gte=start_date
        )

        followups = followups.filter(
            scheduled_at__date__gte=start_date
        )

    if end_date:
        applications = applications.filter(
            created_at__date__lte=end_date
        )

        followups = followups.filter(
            scheduled_at__date__lte=end_date
        )

    pending = applications.filter(
        status__in=[
            "DRAFT",
            "STARTED",
            "SUBMITTED",
            "UNDER_REVIEW",
        ]
    )

    today = timezone.localdate()

    today_followups = followups.filter(
        scheduled_at__date=today,
        status__in=["SCHEDULED", "MISSED"],
    )

    total = leads.count()

    # Lead status history is filtered by the selected date range.
    lead_ids = leads.values("id")

    history = LeadStatusHistory.objects.filter(
        lead_id__in=lead_ids
    )

    if start_date:
        history = history.filter(
            changed_at__date__gte=start_date
        )

    if end_date:
        history = history.filter(
            changed_at__date__lte=end_date
        )

    confirmed = (
        Admission.objects
        .filter(
            application__in=applications,
            status="CONFIRMED",
        )
        .values("lead_id")
        .distinct()
        .count()
    )

    performance = build_performance(
        leads=leads,
        applications=applications,
        followups=followups,
        total_leads=total,
        confirmed_admissions=confirmed,
        history=history,
    )

    return {
        "work_leads": leads,
        "work_applications": applications,
        "work_followups": followups,
        "pending_applications": pending,
        "today_followups": today_followups,
        "performance": performance,
        "recent_activity": recent_activity(
            leads,
            applications,
            followups,
        ),
    }


def build_performance(
    leads,
    applications,
    followups,
    total_leads,
    confirmed_admissions,
    history=None,
):
    """Calculate counsellor funnel and activity performance."""

    if history is None:
        lead_ids = leads.values("id")
    
        history = LeadStatusHistory.objects.filter(
            lead_id__in=lead_ids
        )

    contacted_leads = (
        history
        .filter(new_status="CONTACTED")
        .values("lead_id")
        .distinct()
        .count()
    )

    interested_leads = (
        history
        .filter(new_status="INTERESTED")
        .values("lead_id")
        .distinct()
        .count()
    )

    counselling_leads = (
        history
        .filter(new_status="COUNSELLING")
        .values("lead_id")
        .distinct()
        .count()
    )

    application_leads = (
        history
        .filter(
            new_status__in=[
                "APPLICATION_STARTED",
                "APPLICATION_SUBMITTED",
            ]
        )
        .values("lead_id")
        .distinct()
        .count()
    )

    application_count = applications.count()

    completed_followups = followups.filter(
        status="COMPLETED"
    ).count()

    overdue_followups = followups.filter(
        status__in=["SCHEDULED", "MISSED"],
        scheduled_at__lt=timezone.now(),
    ).count()

    def percentage(value, base):
        return round(value * 100 / base, 1) if base else 0

    return {
        # Existing metrics
        "assigned_leads": total_leads,
        "applications": application_count,
        "pending_applications": applications.filter(
            status__in=[
                "DRAFT",
                "STARTED",
                "SUBMITTED",
                "UNDER_REVIEW",
            ]
        ).count(),
        "confirmed_admissions": confirmed_admissions,
        "completed_followups": completed_followups,
        "overdue_followups": overdue_followups,

        # Funnel counts
        "contacted_leads": contacted_leads,
        "interested_leads": interested_leads,
        "counselling_leads": counselling_leads,
        "application_leads": application_leads,

        # Funnel percentages
        "contacted_rate": percentage(
            contacted_leads,
            total_leads,
        ),
        "interested_rate": percentage(
            interested_leads,
            contacted_leads,
        ),
        "application_rate": percentage(
            application_leads,
            interested_leads,
        ),
        "admission_rate": percentage(
            confirmed_admissions,
            application_count,
        ),

        # Overall conversion
        "conversion_rate": percentage(
            confirmed_admissions,
            total_leads,
        ),
    }


def recent_activity(leads, applications, followups):
    items = []

    for event in (
        LeadStatusHistory.objects
        .filter(lead__in=leads)
        .select_related("lead", "changed_by")
        .order_by("-changed_at", "-pk")[:10]
    ):
        items.append({
            "at": event.changed_at,
            "title": (
                f"{event.lead.full_name}: "
                f"{event.get_new_status_display()}"
            ),
            "actor": event.changed_by.name,
            "url": reverse(
                "leads:detail",
                args=[event.lead_id],
            ),
        })

    for event in (
        LeadNote.objects
        .filter(lead__in=leads)
        .select_related("lead", "created_by")
        .order_by("-created_at", "-pk")[:10]
    ):
        items.append({
            "at": event.created_at,
            "title": f"Note added: {event.lead.full_name}",
            "actor": event.created_by.name,
            "url": reverse(
                "leads:detail",
                args=[event.lead_id],
            ),
        })

    for event in (
        ApplicationStatusHistory.objects
        .filter(application__in=applications)
        .select_related("application", "changed_by")
        .order_by("-changed_at", "-pk")[:10]
    ):
        items.append({
            "at": event.changed_at,
            "title": (
                f"{event.application}: "
                f"{event.get_new_status_display()}"
            ),
            "actor": event.changed_by.name,
            "url": reverse(
                "applications:detail",
                args=[event.application_id],
            ),
        })

    for event in (
        followups
        .select_related("lead", "assigned_to")
        .order_by("-updated_at", "-pk")[:10]
    ):
        items.append({
            "at": event.updated_at,
            "title": (
                f"Follow-up "
                f"{event.get_status_display().lower()}: "
                f"{event.lead.full_name}"
            ),
            "actor": event.assigned_to.name,
            "url": reverse(
                "leads:detail",
                args=[event.lead_id],
            ),
        })

    return sorted(
        items,
        key=lambda item: item["at"],
        reverse=True,
    )[:15]