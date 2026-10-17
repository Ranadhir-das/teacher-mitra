from django.db.models import Count
from django.utils import timezone

from apps.leads.models import Lead
from apps.applications.models import Application, Admission
from apps.followups.models import FollowUp
from apps.accounts.models import User


def lead_report():
    """Return overall lead statistics."""

    queryset = Lead.objects.filter(is_active=True)

    total = queryset.count()

    status_labels = dict(Lead.Status.choices)
    source_labels = dict(Lead.Source.choices)

    status_data = [
        {
            "label": status_labels.get(row["status"], row["status"]),
            "value": row["total"],
        }
        for row in (
            queryset
            .values("status")
            .annotate(total=Count("id"))
            .order_by("-total")
        )
    ]

    source_data = [
        {
            "label": source_labels.get(
                row["lead_source"],
                row["lead_source"],
            ),
            "value": row["total"],
        }
        for row in (
            queryset
            .values("lead_source")
            .annotate(total=Count("id"))
            .order_by("-total")
        )
    ]

    return {
        "total": total,
        "by_status": status_data,
        "by_source": source_data,
    }


def counsellor_report():
    """Return counsellor-wise workload and conversion statistics."""

    counsellors = (
        User.objects
        .filter(
            role=User.Role.COUNSELLOR,
            is_active=True,
        )
        .order_by("name", "id")
    )

    rows = []

    for counsellor in counsellors:
        leads = Lead.objects.filter(
            assigned_counsellor=counsellor,
            is_active=True,
        )

        applications = Application.objects.filter(
            lead__in=leads
        )

        admissions = Admission.objects.filter(
            application__in=applications,
            status=Admission.Status.CONFIRMED,
        )

        followups = FollowUp.objects.filter(
            assigned_to=counsellor,
            lead__in=leads,
        )

        lead_count = leads.count()
        application_count = applications.count()
        admission_count = admissions.values("lead_id").distinct().count()

        conversion_rate = (
            round(admission_count * 100 / lead_count, 1)
            if lead_count
            else 0
        )

        rows.append({
            "label": counsellor.name,
            "leads": lead_count,
            "applications": application_count,
            "admissions": admission_count,
            "completed_followups": followups.filter(
                status=FollowUp.Status.COMPLETED
            ).count(),
            "overdue_followups": followups.filter(
                status__in=[
                    FollowUp.Status.SCHEDULED,
                    FollowUp.Status.MISSED,
                ],
                scheduled_at__lt=timezone.now(),
            ).count(),
            "conversion_rate": conversion_rate,
        })

    return rows


def partner_report():
    """Return partner-wise lead and admission statistics."""

    from apps.partners.models import Partner

    partners = Partner.objects.order_by("business_name", "id")

    rows = []

    for partner in partners:
        leads = Lead.objects.filter(
            partner=partner,
            is_active=True,
        )

        applications = Application.objects.filter(
            lead__in=leads
        )

        admissions = Admission.objects.filter(
            application__in=applications,
            status=Admission.Status.CONFIRMED,
        )

        lead_count = leads.count()
        application_count = applications.count()
        admission_count = admissions.values("lead_id").distinct().count()

        rows.append({
            "label": partner.business_name,
            "leads": lead_count,
            "applications": application_count,
            "admissions": admission_count,
            "conversion_rate": (
                round(admission_count * 100 / lead_count, 1)
                if lead_count
                else 0
            ),
        })

    return rows


def application_report():
    """Return application statistics."""

    queryset = Application.objects.all()

    status_labels = dict(Application.Status.choices)

    return {
        "total": queryset.count(),

        "by_status": [
            {
                "label": status_labels.get(
                    row["status"],
                    row["status"],
                ),
                "value": row["total"],
            }
            for row in (
                queryset
                .values("status")
                .annotate(total=Count("id"))
                .order_by("-total")
            )
        ],

        "by_university": list(
            queryset
            .values(
                "university_id",
                "university__name",
            )
            .annotate(total=Count("id"))
            .order_by("-total")
        ),

        "by_course": list(
            queryset
            .values(
                "course_id",
                "course__name",
            )
            .annotate(total=Count("id"))
            .order_by("-total")
        ),
    }


def admission_report():
    """Return admission statistics."""

    queryset = Admission.objects.all()

    return {
        "total": queryset.count(),

        "confirmed": queryset.filter(
            status=Admission.Status.CONFIRMED
        ).count(),

        "pending": queryset.filter(
            status=Admission.Status.PENDING
        ).count(),

        "cancelled": queryset.filter(
            status=Admission.Status.CANCELLED
        ).count(),

        "by_university": list(
            queryset
            .values(
                "university_id",
                "university__name",
            )
            .annotate(total=Count("id"))
            .order_by("-total")
        ),

        "by_course": list(
            queryset
            .values(
                "course_id",
                "course__name",
            )
            .annotate(total=Count("id"))
            .order_by("-total")
        ),
    }