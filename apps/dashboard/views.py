from datetime import date, timedelta
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.urls import reverse
from django.shortcuts import render
from django.utils import timezone
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.accounts.permissions import can_manage_employees
from apps.applications.models import Application, Admission
from apps.documents.models import Document
from apps.followups.models import FollowUp
from apps.leads.models import Lead
from apps.leads.permissions import visible_leads, optimized, can_create
from apps.partners.models import Partner


def landing(request):
    return render(request, "landing.html")


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()

        # Date Range Filter
        period = self.request.GET.get("period", "month")
        if period not in {"today", "7d", "30d", "month", "prev_month", "year", "custom", "all"}:
            period = "month"
        start_date = None
        end_date = today

        if period == "today":
            start_date = today
        elif period == "7d":
            start_date = today - timedelta(days=6)
        elif period == "30d":
            start_date = today - timedelta(days=29)
        elif period == "month":
            start_date = today.replace(day=1)
        elif period == "prev_month":
            first_this_month = today.replace(day=1)
            last_prev_month = first_this_month - timedelta(days=1)
            start_date = last_prev_month.replace(day=1)
            end_date = last_prev_month
        elif period == "year":
            start_date = today.replace(month=1, day=1)
        elif period == "custom":
            start_raw = self.request.GET.get("start_date", "")
            end_raw = self.request.GET.get("end_date", "")
            try:
                start_date = date.fromisoformat(start_raw)
                end_date = date.fromisoformat(end_raw)
            except ValueError:
                period = "month"
                start_date = today.replace(day=1)
                end_date = today
        elif period == "all":
            start_date = None
            end_date = None

        if start_date and end_date and start_date > end_date:
            start_date, end_date = end_date, start_date

        context["period"] = period
        context["start_date"] = start_date
        context["end_date"] = end_date

        # Counsellor Workload Preservation
        if self.request.user.role == User.Role.COUNSELLOR:
            from apps.accounts.counsellor_queries import counsellor_workload
            context.update(
                counsellor_workload(
                    self.request.user,
                    self.request.user,
                    start_date=start_date,
                    end_date=end_date,
                )
            )
            context["performance_period"] = period
            context["performance_start_date"] = start_date
            context["performance_end_date"] = end_date
            if "today_followups" in context and hasattr(context["today_followups"], "select_related"):
                context["today_followups"] = context["today_followups"].select_related("lead")[:10]
            if "pending_applications" in context and hasattr(context["pending_applications"], "select_related"):
                context["pending_applications"] = context["pending_applications"].select_related("lead", "course")[:10]

        # Scope Leads
        base_queryset = visible_leads(self.request.user).filter(is_active=True)
        if start_date and end_date:
            queryset = base_queryset.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)
        else:
            queryset = base_queryset

        counts = dict(queryset.order_by().values_list("status").annotate(total=Count("id")))
        total_leads_in_period = sum(counts.values())
        all_time_total = base_queryset.count()

        # Follow-ups & Applications
        now = timezone.now()
        overdue_followups = FollowUp.objects.filter(
            lead__in=base_queryset,
            status__in=[FollowUp.Status.SCHEDULED, FollowUp.Status.MISSED],
            scheduled_at__lt=now,
        ).count()

        pending_applications = Application.objects.filter(
            lead__in=base_queryset,
            status__in=[Application.Status.SUBMITTED, Application.Status.UNDER_REVIEW],
        ).count()

        admissions_confirmed = Admission.objects.filter(
            lead__in=queryset,
            status=Admission.Status.CONFIRMED,
        ).values("lead_id").distinct().count()
        conversion_rate = round(admissions_confirmed * 100 / total_leads_in_period, 1) if total_leads_in_period else 0.0

        # Construct KPI Cards
        cards = [
            {
                "label": "Total leads",
                "value": total_leads_in_period,
                "note": f"Filtered period ({period})" if period != 'all' else "All active leads",
                "icon": "leads",
                "url": reverse("leads:list"),
                "variant": "primary",
            },
            {
                "label": "New leads",
                "value": counts.get(Lead.Status.NEW, 0),
                "note": "Awaiting initial contact",
                "icon": "add",
                "url": f"{reverse('leads:list')}?status=NEW",
            },
            {
                "label": "Assigned leads",
                "value": counts.get(Lead.Status.ASSIGNED, 0),
                "note": "Assigned to counsellors",
                "icon": "employees",
                "url": f"{reverse('leads:list')}?status=ASSIGNED",
            },
            {
                "label": "Interested leads",
                "value": counts.get(Lead.Status.INTERESTED, 0),
                "note": "Actively engaged",
                "icon": "students",
                "url": f"{reverse('leads:list')}?status=INTERESTED",
            },
            {
                "label": "Counselling leads",
                "value": counts.get(Lead.Status.COUNSELLING, 0),
                "note": "In counselling phase",
                "icon": "profile",
                "url": f"{reverse('leads:list')}?status=COUNSELLING",
            },
            {
                "label": "Lost leads",
                "value": counts.get(Lead.Status.LOST, 0),
                "note": "Not moving forward",
                "icon": "alert",
                "url": f"{reverse('leads:list')}?status=LOST",
            },
        ]

        if can_manage_employees(self.request.user):
            total_partners = Partner.objects.count()
            active_partners = Partner.objects.filter(status=Partner.Status.ACTIVE).count()
            pending_onboarding = Partner.objects.filter(status=Partner.Status.SUBMITTED).count()
            partner_leads_count = queryset.filter(partner__isnull=False).count()
            active_employees_count = User.objects.filter(is_active=True).exclude(role=User.Role.PARTNER).count()

            cards.extend([
                {"label": "Active employees", "value": active_employees_count, "note": "Live internal account count", "icon": "employees", "url": reverse("accounts:employee-list")},
                {"label": "Total partners", "value": total_partners, "note": "Registered partners", "icon": "partners", "url": reverse("partners:list")},
                {"label": "Active partners", "value": active_partners, "note": "Approved partners", "icon": "check", "url": f"{reverse('partners:list')}?status=ACTIVE"},
                {"label": "Partner leads", "value": partner_leads_count, "note": "Active attributed leads", "icon": "leads"},
            ])
            context["pending_onboarding_count"] = pending_onboarding
            context["pending_documents_count"] = Document.objects.filter(
                partner__isnull=False,
                status=Document.Status.SUBMITTED,
                deleted_at__isnull=True,
            ).count()

        # Funnel Sequential Stages
        # Contacted = all from contacted onward
        contacted_statuses = [
            Lead.Status.CONTACTED, Lead.Status.INTERESTED, Lead.Status.COUNSELLING,
            Lead.Status.COURSE_SELECTED, Lead.Status.APPLICATION_STARTED,
            Lead.Status.APPLICATION_SUBMITTED, Lead.Status.PAYMENT_PENDING,
            Lead.Status.ADMISSION_CONFIRMED
        ]
        interested_statuses = [
            Lead.Status.INTERESTED, Lead.Status.COUNSELLING, Lead.Status.COURSE_SELECTED,
            Lead.Status.APPLICATION_STARTED, Lead.Status.APPLICATION_SUBMITTED,
            Lead.Status.PAYMENT_PENDING, Lead.Status.ADMISSION_CONFIRMED
        ]
        course_selected_statuses = [
            Lead.Status.COURSE_SELECTED, Lead.Status.APPLICATION_STARTED,
            Lead.Status.APPLICATION_SUBMITTED, Lead.Status.PAYMENT_PENDING,
            Lead.Status.ADMISSION_CONFIRMED
        ]
        application_statuses = [
            Lead.Status.APPLICATION_STARTED, Lead.Status.APPLICATION_SUBMITTED,
            Lead.Status.PAYMENT_PENDING, Lead.Status.ADMISSION_CONFIRMED
        ]

        funnel_stages = [
            {"label": "Total Inflow", "count": total_leads_in_period, "percent": 100 if total_leads_in_period else 0},
            {"label": "Contacted", "count": sum(counts.get(s, 0) for s in contacted_statuses), "percent": round(sum(counts.get(s, 0) for s in contacted_statuses) * 100 / total_leads_in_period) if total_leads_in_period else 0},
            {"label": "Interested / Counselling", "count": sum(counts.get(s, 0) for s in interested_statuses), "percent": round(sum(counts.get(s, 0) for s in interested_statuses) * 100 / total_leads_in_period) if total_leads_in_period else 0},
            {"label": "Course Selected", "count": sum(counts.get(s, 0) for s in course_selected_statuses), "percent": round(sum(counts.get(s, 0) for s in course_selected_statuses) * 100 / total_leads_in_period) if total_leads_in_period else 0},
            {"label": "Applications", "count": sum(counts.get(s, 0) for s in application_statuses), "percent": round(sum(counts.get(s, 0) for s in application_statuses) * 100 / total_leads_in_period) if total_leads_in_period else 0},
            {"label": "Admissions Confirmed", "count": admissions_confirmed, "percent": round(admissions_confirmed * 100 / total_leads_in_period) if total_leads_in_period else 0},
        ]

        # Monthly lead creation and confirmed admission activity (last 6 calendar months).
        month_starts = [today.replace(day=1)]
        for _ in range(5):
            month_starts.insert(0, month_starts[0] - timedelta(days=1))
            month_starts[0] = month_starts[0].replace(day=1)
        six_months_ago = month_starts[0]
        lead_months = list(
            base_queryset.filter(created_at__date__gte=six_months_ago)
            .annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(total=Count("id"))
            .order_by("month")
        )
        admission_months = list(
            Admission.objects.filter(
                lead__in=base_queryset,
                status=Admission.Status.CONFIRMED,
                admission_date__gte=six_months_ago,
                admission_date__lte=today,
            )
            .annotate(month=TruncMonth("admission_date"))
            .values("month")
            .annotate(total=Count("id"))
            .order_by("month")
        )
        month_map = {
            month.strftime("%b %Y"): {"month": month.strftime("%b %Y"), "leads": 0, "admissions": 0}
            for month in month_starts
        }
        for r in lead_months:
            m_str = r["month"].strftime("%b %Y") if r["month"] else ""
            if m_str in month_map:
                month_map[m_str]["leads"] = r["total"]
        for r in admission_months:
            m_str = r["month"].strftime("%b %Y") if r["month"] else ""
            if m_str in month_map:
                month_map[m_str]["admissions"] = r["total"]

        trend_labels = list(month_map.keys())
        trend_leads = [month_map[k]["leads"] for k in trend_labels]
        trend_admissions = [month_map[k]["admissions"] for k in trend_labels]

        # Status Chart Data (Doughnut)
        status_chart_data = [
            {"label": label, "value": counts.get(value, 0)}
            for value, label in Lead.Status.choices if counts.get(value, 0)
        ]

        # Sources Chart Data (Bar)
        source_labels_dict = dict(Lead.Source.choices)
        sources_data = [
            {"label": source_labels_dict.get(row["lead_source"], row["lead_source"]), "count": row["total"]}
            for row in queryset.order_by().values("lead_source").annotate(total=Count("id")).order_by("-total", "lead_source")[:7]
        ]

        # Recent Leads
        recent_leads = optimized(queryset)[:6]

        period_choices = [
            ("today", "Today"),
            ("7d", "7 days"),
            ("30d", "30 days"),
            ("month", "This month"),
            ("prev_month", "Last month"),
            ("year", "This year"),
            ("all", "All time"),
        ]

        context.update(
            cards=cards,
            recent_leads=recent_leads,
            can_create_lead=can_create(self.request.user),
            can_manage_employees=can_manage_employees(self.request.user),
            total_leads_in_period=total_leads_in_period,
            all_time_total=all_time_total,
            overdue_followups=overdue_followups,
            pending_application_count=pending_applications,
            admissions_confirmed=admissions_confirmed,
            conversion_rate=conversion_rate,
            funnel_stages=funnel_stages,
            status_chart_data=status_chart_data,
            trend_chart_data={"labels": trend_labels, "leads": trend_leads, "admissions": trend_admissions},
            sources_data=sources_data,
            period_choices=period_choices,
            # For backward compatibility with existing template snippets:
            distribution=[
                {"label": label, "count": counts.get(value, 0), "percent": round(counts.get(value, 0) * 100 / total_leads_in_period) if total_leads_in_period else 0}
                for value, label in Lead.Status.choices if counts.get(value, 0)
            ],
            sources=sources_data,
        )
        return context
