from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from apps.accounts.permissions import is_internal_user
from apps.leads.permissions import visible_leads
from apps.documents.models import DocumentHistory
from .forms import ApplicationForm
from .models import Application
from .permissions import application_leads, visible_applications
from .services import EDITABLE_FIELDS, save_application


def check_access(user):
    if not is_internal_user(user):
        raise PermissionDenied


@login_required
@require_http_methods(["GET"])
def application_list(request):
    check_access(request.user)
    queryset = visible_applications(request.user).select_related("lead", "university", "course")
    search = request.GET.get("search", "").strip()
    status = request.GET.get("status", "")
    if search:
        queryset = queryset.filter(Q(reference__icontains=search) | Q(lead__full_name__icontains=search) | Q(course__name__icontains=search))
    if status:
        queryset = queryset.filter(status=status)
    if request.GET.get("lead"):
        value = request.GET["lead"]
        queryset = queryset.filter(lead_id=value) if value.isdecimal() else queryset.none()
    query = request.GET.copy()
    query.pop("page", None)
    return render(request, "applications/list.html", {"page_obj": Paginator(queryset, 25).get_page(request.GET.get("page")),
        "search": search, "selected_status": status, "status_choices": Application.Status.choices, "query": query.urlencode()})


@login_required
@require_http_methods(["GET"])
def application_detail(request, pk):
    check_access(request.user)
    application = get_object_or_404(visible_applications(request.user).select_related("lead", "university", "course", "created_by", "updated_by"), pk=pk)
    return render(request, "applications/detail.html", {"application": application,
        "documents": application.documents.select_related("reviewed_by"),
        "document_history": DocumentHistory.objects.filter(document__application=application).select_related("actor", "document"),
        "admission": getattr(application, "admission", None),
        "admission_history": application.admission.history.select_related("actor") if hasattr(application, "admission") else [],
        "history": application.history.select_related("changed_by"),
        "can_view_lead": visible_leads(request.user).filter(pk=application.lead_id).exists()})


@login_required
@require_http_methods(["GET", "POST"])
def application_edit(request, pk=None):
    check_access(request.user)
    application = get_object_or_404(visible_applications(request.user), pk=pk) if pk else None
    initial = {}
    if not pk and request.GET.get("lead"):
        value = request.GET["lead"]
        lead = get_object_or_404(application_leads(request.user), pk=value if value.isdecimal() else 0)
        initial = {"lead": lead, "university": lead.selected_university_id, "course": lead.selected_course_id,
            "academic_details": "\n".join(str(value) for value in (lead.highest_qualification, lead.institution_name,
                lead.passing_year, lead.percentage_or_cgpa, lead.specialization) if value)}
    form = ApplicationForm(request.POST if request.method == "POST" else None, instance=application, actor=request.user, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            application = save_application(request.user, {field: form.cleaned_data[field] for field in EDITABLE_FIELDS},
                pk=pk, lead_id=form.cleaned_data["lead"].pk)
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, "Application saved.")
            return redirect("applications:detail", pk=application.pk)
    return render(request, "applications/form.html", {"form": form, "application": application})
