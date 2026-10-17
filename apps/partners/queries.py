from django.db.models import Count, Q
from .forms import PartnerFilterForm, PortalLeadFilterForm
from .statuses import PUBLIC_STATUSES, public_status


def partner_list(queryset, params):
    form = PartnerFilterForm(params)
    queryset = queryset.select_related("user").annotate(total_leads=Count("leads"))
    if not form.is_valid():
        return queryset.none(), form
    data = form.cleaned_data
    if data.get("search"):
        term = data["search"]
        queryset = queryset.filter(Q(partner_code__icontains=term) | Q(business_name__icontains=term) | Q(contact_person__icontains=term) | Q(phone__icontains=term) | Q(email__icontains=term))
    for key in ("status", "partner_type"):
        if data.get(key):
            queryset = queryset.filter(**{key: data[key]})
    ordering = {"newest": "-created_at", "oldest": "created_at", "name": "business_name", "leads": "-total_leads"}
    return queryset.order_by(ordering.get(data.get("sort"), "-created_at"), "-pk"), form


def portal_leads(queryset, params):
    form = PortalLeadFilterForm(params)
    if not form.is_valid():
        return queryset.none(), form
    data = form.cleaned_data
    if data.get("search"):
        term = data["search"]
        queryset = queryset.filter(Q(full_name__icontains=term) | Q(phone__icontains=term) | Q(email__icontains=term) | Q(desired_course__icontains=term))
    if data.get("status"):
        queryset = queryset.filter(status__in=PUBLIC_STATUSES[data["status"]][1])
    ordering = {"newest": "-created_at", "oldest": "created_at", "name": "full_name", "updated": "-updated_at"}
    return queryset.order_by(ordering.get(data.get("sort"), "-created_at"), "-pk"), form


def portal_cards(queryset):
    counts = dict(queryset.order_by().values_list("status").annotate(total=Count("id")))
    cards = [{"label": "Total leads submitted", "value": sum(counts.values()), "note": "Your referrals"}]
    for code, (label, statuses) in PUBLIC_STATUSES.items():
        cards.append({"label": label, "value": sum(counts.get(s, 0) for s in statuses), "note": "Current referral progress"})
    return cards


def decorate_leads(leads):
    for lead in leads:
        lead.public_progress = public_status(lead)
    return leads


def partner_report(queryset):
    """Aggregate only the already ownership-scoped queryset; never include private notes."""
    from datetime import timedelta
    import math
    import textwrap
    from django.db.models.functions import TruncDate
    from django.utils import timezone
    from apps.leads.models import Lead, LeadStatusHistory

    counts = dict(queryset.order_by().values_list("status").annotate(total=Count("pk")))
    total = sum(counts.values())
    colors = ["#3b82f6", "#8b5cf6", "#06b6d4", "#f59e0b", "#ec4899", "#84cc16", "#6366f1", "#f97316", "#14b8a6", "#22c55e", "#f43f5e", "#64748b", "#a855f7", "#ef4444"]
    rows, stops, position = [], [], 0
    groups = [(code, label, {code}) for code, label in Lead.Status.choices if code not in {"LOST", "NOT_INTERESTED"}]
    groups.append(("LOST", "Lost / Not Interested", {"LOST", "NOT_INTERESTED"}))
    for index, (code, label, statuses) in enumerate(groups):
        value = sum(counts.get(status, 0) for status in statuses)
        end = position + (value / total * 100 if total else 0)
        color = colors[index % len(colors)]
        stops.append(f"{color} {position:.4f}% {end:.4f}%")
        rows.append({"code": code, "label": label, "value": value, "color": color, "percentage": round(value / total * 100, 1) if total else 0})
        position = end
    # Fixed SVG coordinates scale with the container. Tiny slices remain in the
    # legend rather than placing overlapping labels inside the chart.
    populated = sum(row["value"] > 0 for row in rows)
    offset = 0
    for row in rows:
        share = row["value"] / total * 100 if total else 0
        angle = math.radians((offset + share / 2) * 3.6 - 90)
        row.update({
            "arc": f"{share:.6f} {100 - share:.6f}",
            "offset": f"{-offset:.6f}",
            "percent_x": f"{250 + 190 * math.cos(angle):.2f}",
            "percent_y": f"{250 + 190 * math.sin(angle):.2f}",
            "label_x": f"{250 + 94 * math.cos(angle):.2f}",
            "label_y": f"{250 + 94 * math.sin(angle):.2f}",
            "label_lines": textwrap.wrap(row["label"], width=15),
            "show_percentage": share >= 4,
            "show_label": share >= 6 and populated <= 8,
        })
        offset += share
    today = timezone.localdate()
    start = today - timedelta(days=29)
    daily = dict(queryset.filter(created_at__date__gte=start, created_at__date__lte=today).order_by()
                 .annotate(day=TruncDate("created_at")).values_list("day").annotate(total=Count("pk")))
    peak = max(daily.values(), default=1) or 1
    trend = [{"day": start + timedelta(days=i), "value": daily.get(start + timedelta(days=i), 0),
              "height": round(daily.get(start + timedelta(days=i), 0) / peak * 100, 2)} for i in range(30)]
    activity = list(LeadStatusHistory.objects.filter(lead__in=queryset).order_by("-changed_at", "-pk")
                    .values("lead_id", "lead__full_name", "new_status", "changed_at")[:10])
    labels = dict(Lead.Status.choices)
    for item in activity:
        item["label"] = labels.get(item.pop("new_status"), "Updated")
    return {"report_total": total, "status_rows": rows, "donut_gradient": ", ".join(stops) if total else "#e7ede9 0% 100%",
            "trend": trend, "trend_total": sum(daily.values()), "activity": activity}
