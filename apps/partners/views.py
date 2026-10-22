from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from django.views.decorators.debug import sensitive_post_parameters
from apps.leads.views import form_error
from apps.leads.models import Lead
from .models import Partner
from .permissions import manager_required, partner_required, onboarding_required
from .forms import PartnerForm, LoginAccountForm, PartnerStatusForm, AccountAccessForm, ProfileForm, SubmissionForm
from .queries import partner_list, portal_leads, portal_cards, decorate_leads
from . import services


@manager_required
def index(request):
    queryset, form = partner_list(Partner.objects.all(), request.GET)
    page = Paginator(queryset, 20).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return render(request, "partners/list.html", {"page_obj": page, "form": form, "query": query.urlencode()})


@manager_required
def detail(request, pk):
    partner = get_object_or_404(Partner.objects.select_related("user", "created_by"), pk=pk)
    leads = partner.leads.all()
    cards = [
        {"label": "Total leads", "value": leads.count(), "note": "Attributed referrals"},
        {"label": "Active leads", "value": leads.filter(is_active=True).count(), "note": "Not archived"},
        {"label": "Interested leads", "value": leads.filter(status=Lead.Status.INTERESTED).count(), "note": "Current lead status"},
        {"label": "Admission confirmed", "value": leads.filter(status=Lead.Status.ADMISSION_CONFIRMED).count(), "note": "Lead status, not admission records"},
    ]
    return render(request, "partners/detail.html", {"partner": partner, "cards": cards, "recent_leads": leads[:5]})


@sensitive_post_parameters("password", "password_confirm")
@manager_required
@require_http_methods(["GET", "POST"])
def edit(request, pk=None):
    partner = get_object_or_404(Partner, pk=pk) if pk else None
    form = PartnerForm(request.POST if request.method == "POST" else None, instance=partner)
    if request.method == "POST" and form.is_valid():
        data = {field: form.cleaned_data[field] for field in services.PARTNER_FIELDS}
        try:
            if partner:
                result = services.update_partner(request.user, partner.pk, data)
            else:
                result = services.create_partner(request.user, data, create_login=form.cleaned_data["create_login"],
                    login_email=form.cleaned_data["login_email"], password=form.cleaned_data["password"])
        except ValidationError as exc:
            form_error(form, exc)
        else:
            messages.success(request, "Partner saved successfully.")
            return redirect("partners:detail", pk=result.pk)
    return render(request, "partners/form.html", {"form": form, "partner": partner})


@sensitive_post_parameters("password", "password_confirm")
@manager_required
@require_http_methods(["GET", "POST"])
def action(request, pk, action):
    partner = get_object_or_404(Partner, pk=pk)
    if action == "account":
        form = LoginAccountForm(request.POST if request.method == "POST" else None, initial={"login_email": partner.email})
        title = "Create login account"
    elif action == "account-access":
        form = AccountAccessForm(request.POST if request.method == "POST" else None)
        title = "Manage login access"
    else:
        form = PartnerStatusForm(request.POST if request.method == "POST" else None, initial={"status": partner.status})
        title = "Change partner status"
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            if action == "account":
                services.create_login(request.user, pk, data["login_email"], data["password"])
            elif action == "account-access":
                services.account_access(request.user, pk, data["is_active"])
            else:
                services.update_partner(request.user, pk, {"status": data["status"]})
        except ValidationError as exc:
            form_error(form, exc)
        else:
            messages.success(request, "Partner account updated.")
            return redirect("partners:detail", pk=pk)
    return render(request, "partners/action.html", {"partner": partner, "form": form, "title": title})


@onboarding_required
def portal_dashboard(request):
    if request.partner.status != "ACTIVE":
        from .onboarding import progress
        return render(request, "partner_portal/limited.html", {"partner": request.partner, "progress": progress(request.partner)})
    queryset = request.partner.leads.all()

    # Chart data: status doughnut
    from django.db.models import Count
    from .statuses import PUBLIC_STATUSES
    counts = dict(queryset.order_by().values_list("status").annotate(total=Count("id")))
    chart_status_data = []
    for code, (label, statuses) in PUBLIC_STATUSES.items():
        value = sum(counts.get(s, 0) for s in statuses)
        if value:
            chart_status_data.append({"label": label, "value": value})

    # Chart data: 30-day trend
    from datetime import timedelta
    from django.db.models.functions import TruncDate
    from django.utils import timezone
    today = timezone.localdate()
    start = today - timedelta(days=29)
    daily = dict(
        queryset.filter(created_at__date__gte=start, created_at__date__lte=today)
        .order_by().annotate(day=TruncDate("created_at"))
        .values_list("day").annotate(total=Count("pk"))
    )
    trend_labels = [(start + timedelta(days=i)).strftime("%d %b") for i in range(30)]
    trend_values = [daily.get(start + timedelta(days=i), 0) for i in range(30)]

    return render(request, "partner_portal/dashboard.html", {
        "partner": request.partner,
        "cards": portal_cards(queryset),
        "recent_leads": decorate_leads(list(queryset[:5])),
        "chart_status_data": chart_status_data,
        "chart_trend_data": {"labels": trend_labels, "values": trend_values},
    })


@partner_required
def portal_list(request):
    queryset, form = portal_leads(request.partner.leads.all(), request.GET)
    page = Paginator(queryset, 20).get_page(request.GET.get("page"))
    decorate_leads(page.object_list)
    query = request.GET.copy()
    query.pop("page", None)
    return render(request, "partner_portal/leads.html", {"partner": request.partner, "form": form, "page_obj": page, "query": query.urlencode()})


@partner_required
def portal_detail(request, pk):
    lead = get_object_or_404(request.partner.leads.all(), pk=pk)
    decorate_leads([lead])
    values = [(lead._meta.get_field(field).verbose_name, getattr(lead, f"get_{field}_display")() if lead._meta.get_field(field).choices else getattr(lead, field)) for field in services.SUBMISSION_FIELDS]
    # Project only partner-safe fields from this already ownership-scoped lead.
    # Internal notes, assignment reasons and staff identities stay in the CRM.
    labels = dict(Lead.Status.choices)
    events = lead.status_history.order_by("-changed_at", "-pk").values(
        "previous_status", "new_status", "changed_at"
    )
    logs = Paginator(events, 20).get_page(request.GET.get("log_page"))
    for event in logs.object_list:
        event["previous_label"] = labels.get(event["previous_status"], "Submitted")
        event["new_label"] = labels.get(event["new_status"], "Updated")
    return render(request, "partner_portal/detail.html", {"partner": request.partner,
        "lead": lead, "values": values, "student_logs": logs,
        "can_edit": services.can_edit_submission(request.user, lead)})


@partner_required
@require_http_methods(["GET", "POST"])
def portal_submit(request, pk=None):
    lead = get_object_or_404(request.partner.leads.all(), pk=pk) if pk else None
    if lead and not services.can_edit_submission(request.user, lead):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("This referral is already being processed.")
    form = SubmissionForm(request.POST if request.method == "POST" else None, instance=lead)
    if request.method == "POST" and form.is_valid():
        # Ignore no hidden ownership inputs: unknown submitted fields are rejected.
        unknown = set(request.POST) - set(form.fields) - {"csrfmiddlewaretoken"}
        if unknown:
            form.add_error(None, "The submission contains fields that are not permitted.")
        else:
            try:
                data = {field: form.cleaned_data[field] for field in services.SUBMISSION_FIELDS}
                if lead:
                    result = services.edit_submission(request.user, lead.pk, data, confirm_duplicate=form.cleaned_data["confirm_duplicate"])
                else:
                    result = services.submit_lead(request.user, data, confirm_duplicate=form.cleaned_data["confirm_duplicate"])
            except ValidationError as exc:
                form_error(form, exc)
            else:
                messages.success(request, "Your referral has been saved.")
                return redirect("partner-portal:detail", pk=result.pk)
    return render(request, "partner_portal/form.html", {"partner": request.partner, "form": form, "lead": lead})


@partner_required
@require_http_methods(["GET", "POST"])
def portal_profile(request):
    form = ProfileForm(request.POST if request.method == "POST" else None, instance=request.partner)
    if request.method == "POST" and form.is_valid():
        if set(request.POST) - set(form.fields) - {"csrfmiddlewaretoken"}:
            form.add_error(None, "Only the displayed contact fields can be updated.")
        else:
            try:
                services.update_profile(request.user, form.cleaned_data)
            except ValidationError as exc:
                form_error(form, exc)
            else:
                messages.success(request, "Profile updated. Your login email has not changed.")
                return redirect("partner-portal:profile")
    return render(request, "partner_portal/profile.html", {"partner": request.partner, "form": form})


@sensitive_post_parameters("password", "password_confirm")
@require_http_methods(["GET", "POST"])
def signup(request):
    from .forms import PartnerSignupForm
    if request.user.is_authenticated:
        return redirect("partner-portal:dashboard" if request.user.role == "PARTNER" else "dashboard:index")
    form = PartnerSignupForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        if set(request.POST) - set(form.fields) - {"csrfmiddlewaretoken"}:
            form.add_error(None, "Only the displayed registration fields are permitted.")
        else:
            try:
                services.register_partner({key: form.cleaned_data[key] for key in services.SIGNUP_FIELDS}, form.cleaned_data["password"])
            except ValidationError as exc:
                form_error(form, exc)
            else:
                messages.success(request, "Account created. Sign in to complete onboarding and submit it for approval.")
                return redirect("accounts:login")
    return render(request, "partner_portal/signup.html", {"form": form})


@manager_required
@require_http_methods(["POST"])
def review(request, pk, decision):
    get_object_or_404(Partner, pk=pk)
    try:
        services.review_registration(request.user, pk, approve=decision == "approve")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Partner registration approved." if decision == "approve" else "Partner registration rejected.")
    return redirect("partners:detail", pk=pk)


@partner_required
def portal_reports(request):
    from .queries import partner_report
    return render(request, "partner_portal/reports.html", {"partner": request.partner, **partner_report(request.partner.leads.all())})


@manager_required
@require_http_methods(["GET", "POST"])
def delete(request, pk):
    from django.db.models.deletion import ProtectedError
    from django.urls import reverse
    partner = get_object_or_404(Partner, pk=pk)
    if request.method == "POST":
        try:
            services.delete_partner(request.user, pk)
        except ProtectedError:
            messages.error(request, "This partner has linked CRM records, documents or audit history and cannot be deleted. Deactivate the partner instead.")
            return redirect("partners:detail", pk=pk)
        messages.success(request, "Partner and associated login deleted.")
        return redirect("partners:list")
    return render(request, "accounts/delete_confirm.html", {"object_name": partner.business_name,
        "kind": "partner", "cancel_url": reverse("partners:detail", args=[pk])})
