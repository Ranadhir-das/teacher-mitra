import csv
from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.core.paginator import Paginator
from django.http import StreamingHttpResponse
from django.views.generic import TemplateView
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.permissions import can_manage_employees
from apps.applications.models import Admission, Application
from apps.documents.models import Document
from apps.followups.models import FollowUp
from apps.leads.models import Lead
from apps.partners.models import Partner
from apps.leads.csv_utils import safe_csv_cell

from .services import lead_report, report_leads


class Echo:
    def write(self, value):
        return value


def _filters(request):
    errors = []
    start_date = end_date = None
    for name in ("start_date", "end_date"):
        raw = request.GET.get(name, "").strip()
        if raw:
            try:
                parsed = date.fromisoformat(raw)
                if name == "start_date":
                    start_date = parsed
                else:
                    end_date = parsed
            except ValueError:
                errors.append(f"Enter a valid {name.replace('_', ' ')}.")
    if start_date and end_date and start_date > end_date:
        errors.append("Start date must be on or before end date.")
        start_date = end_date = None
    status = request.GET.get("status", "")
    if status and status not in Lead.Status.values:
        errors.append("Choose a valid lead status.")
        status = ""
    sort = request.GET.get("sort", "recent")
    if sort not in {"recent", "oldest", "student", "status"}:
        errors.append("Choose a valid sort order.")
        sort = "recent"
    return start_date, end_date, status, sort, errors


def _authorized(user):
    return user.role in {User.Role.SUPER_ADMIN, User.Role.ADMIN, User.Role.TEAM_LEADER}


class ReportsDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "reports/dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if not _authorized(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        start_date, end_date, status, sort, errors = _filters(self.request)
        leads = report_leads(self.request.user, start_date=start_date, end_date=end_date, status=status, sort=sort)
        if errors:
            leads = leads.none()
        report = lead_report(leads)
        monthly_rows = list(
            leads.order_by().annotate(month=TruncMonth("created_at"))
            .values("month").annotate(total=Count("id"))
            .order_by("-month")[:12]
        )
        monthly_rows.reverse()
        lead_trend_data = {
            "labels": [row["month"].strftime("%b %Y") for row in monthly_rows if row["month"]],
            "values": [row["total"] for row in monthly_rows if row["month"]],
        }
        # Related records in these summaries are restricted through the visible lead queryset.
        applications = Application.objects.filter(lead__in=leads)
        admissions = Admission.objects.filter(application__in=applications)
        status_labels = dict(Application.Status.choices)
        application_status = [
            {"label": status_labels.get(row["status"], row["status"]), "value": row["total"]}
            for row in applications.order_by().values("status").annotate(total=Count("id")).order_by("-total")
        ]
        counsellor_rows = list(
            leads.order_by().values("assigned_counsellor_id", "assigned_counsellor__name")
            .annotate(leads=Count("id", distinct=True), applications=Count("applications", distinct=True),
                      admissions=Count("admissions", filter=Q(admissions__status=Admission.Status.CONFIRMED), distinct=True))
            .order_by("assigned_counsellor__name")
        )
        partner_rows = list(
            leads.filter(partner__isnull=False).order_by().values("partner_id", "partner__business_name")
            .annotate(leads=Count("id", distinct=True), applications=Count("applications", distinct=True),
                      admissions=Count("admissions", filter=Q(admissions__status=Admission.Status.CONFIRMED), distinct=True))
            .order_by("partner__business_name")
        )
        counsellor_rows = [{"label": row["assigned_counsellor__name"] or "Unassigned", **{key: row[key] for key in ("leads", "applications", "admissions")}} for row in counsellor_rows]
        partner_rows = [{"label": row["partner__business_name"], **{key: row[key] for key in ("leads", "applications", "admissions")}} for row in partner_rows]
        followups = FollowUp.objects.filter(lead__in=leads)
        followup_summary = {
            "completed": followups.filter(status=FollowUp.Status.COMPLETED).count(),
            "overdue": followups.filter(status__in=[FollowUp.Status.SCHEDULED, FollowUp.Status.MISSED], scheduled_at__lt=timezone.now()).count(),
        }
        partner_ids = leads.exclude(partner__isnull=True).values("partner_id").distinct()
        partners = Partner.objects.all() if can_manage_employees(self.request.user) else Partner.objects.filter(pk__in=partner_ids)
        documents = Document.objects.filter(partner__in=partners, deleted_at__isnull=True)
        partner_labels = dict(Partner.Status.choices)
        document_labels = dict(Document.Status.choices)
        onboarding_summary = {
            "partners": [
                {"label": partner_labels.get(row["status"], row["status"]), "total": row["total"]}
                for row in partners.order_by().values("status").annotate(total=Count("id")).order_by("status")
            ],
            "documents": [
                {"label": document_labels.get(row["status"], row["status"]), "total": row["total"]}
                for row in documents.order_by().values("status").annotate(total=Count("id")).order_by("status")
            ],
        }
        lead_page = Paginator(report["rows"], 50).get_page(self.request.GET.get("page"))
        context.update(
            lead_report=report,
            lead_trend_data=lead_trend_data,
            application_report={"total": applications.count(), "by_status": application_status},
            admission_report={
                "total": admissions.count(),
                "confirmed": admissions.filter(status=Admission.Status.CONFIRMED).count(),
                "pending": admissions.filter(status=Admission.Status.PENDING).count(),
                "cancelled": admissions.filter(status=Admission.Status.CANCELLED).count(),
                "by_status": [
                    {"label": dict(Admission.Status.choices).get(row["status"], row["status"]), "value": row["total"]}
                    for row in admissions.order_by().values("status").annotate(total=Count("id")).order_by("-total")
                ],
            },
            counsellor_report=counsellor_rows,
            partner_report=partner_rows,
            followup_report=followup_summary,
            onboarding_report=onboarding_summary,
            lead_page=lead_page,
            start_date=start_date,
            end_date=end_date,
            selected_status=status,
            selected_sort=sort,
            status_choices=Lead.Status.choices,
            sort_choices=(("recent", "Newest first"), ("oldest", "Oldest first"), ("student", "Student name"), ("status", "Status")),
            filter_errors=errors,
        )
        return context


class LeadCSVExportView(LoginRequiredMixin, TemplateView):
    """Stream a minimal, permission-scoped lead report."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if not _authorized(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        start_date, end_date, status, sort, errors = _filters(request)
        if errors:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest(" ".join(errors))
        queryset = report_leads(request.user, start_date=start_date, end_date=end_date, status=status, sort=sort)

        def rows():
            writer = csv.writer(Echo())
            yield writer.writerow(["Lead ID", "Student", "Status", "Source", "Created", "Partner", "Counsellor"])
            for lead in queryset.select_related("partner", "assigned_counsellor").iterator(chunk_size=500):
                yield writer.writerow([
                    lead.pk, safe_csv_cell(lead.full_name), safe_csv_cell(lead.get_status_display()),
                    safe_csv_cell(lead.get_lead_source_display()), timezone.localtime(lead.created_at).isoformat(),
                    safe_csv_cell(lead.partner.business_name if lead.partner_id else ""),
                    safe_csv_cell(lead.assigned_counsellor.name if lead.assigned_counsellor_id else ""),
                ])

        response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="lead-report.csv"'
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response
