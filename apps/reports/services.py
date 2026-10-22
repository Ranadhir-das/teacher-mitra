from django.db.models import Count

from apps.leads.models import Lead
from apps.leads.permissions import visible_leads


def report_leads(user, *, start_date=None, end_date=None, status="", sort="recent"):
    """Return only leads visible to the requesting employee and matching filters."""
    queryset = visible_leads(user).filter(is_active=True)
    if start_date:
        queryset = queryset.filter(created_at__date__gte=start_date)
    if end_date:
        queryset = queryset.filter(created_at__date__lte=end_date)
    if status in Lead.Status.values:
        queryset = queryset.filter(status=status)
    ordering = {"recent": ("-created_at", "-pk"), "oldest": ("created_at", "pk"),
                "student": ("full_name", "pk"), "status": ("status", "-created_at", "-pk")}
    return queryset.order_by(*ordering.get(sort, ordering["recent"]))


def lead_report(queryset):
    status_labels = dict(Lead.Status.choices)
    source_labels = dict(Lead.Source.choices)
    by_status = list(queryset.order_by().values("status").annotate(total=Count("id")).order_by("-total", "status"))
    by_source = list(queryset.order_by().values("lead_source").annotate(total=Count("id")).order_by("-total", "lead_source"))
    return {
        "total": queryset.count(),
        "by_status": [{"label": status_labels.get(row["status"], row["status"]), "value": row["total"]} for row in by_status],
        "by_source": [{"label": source_labels.get(row["lead_source"], row["lead_source"]), "value": row["total"]} for row in by_source],
        "rows": queryset.select_related("partner", "assigned_counsellor"),
    }
