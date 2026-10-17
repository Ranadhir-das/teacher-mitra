from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from .permissions import onboarding_required, manager_required
from .models import Partner
from .onboarding_forms import OnboardingForm, UploadForm, ReviewForm
from . import onboarding as service


@onboarding_required
@require_http_methods(["GET", "POST"])
def edit(request):
    form = OnboardingForm(request.POST if request.method == "POST" else None, instance=request.partner)
    if request.method == "POST" and form.is_valid():
        try:
            service.check_fields({key: value for key, value in request.POST.items() if key != "csrfmiddlewaretoken"}, service.FIELDS)
            service.save_draft(request.user, form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, "Onboarding draft saved.")
            return redirect("partner-portal:onboarding")
    return render(request, "partner_portal/onboarding.html", {"partner": request.partner, "form": form,
        "upload_form": UploadForm(), "progress": service.progress(request.partner),
        "documents": request.partner.onboarding_documents.filter(deleted_at__isnull=True),
        "can_edit": request.partner.status in service.EDITABLE_STATUSES})


@onboarding_required
@require_http_methods(["POST"])
def upload(request):
    form = UploadForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            service.upload_document(request.user, form.cleaned_data["document_type"], form.cleaned_data["file"])
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            messages.success(request, "Document uploaded.")
    else:
        messages.error(request, "; ".join(message for errors in form.errors.values() for message in errors))
    return redirect("partner-portal:onboarding")


@onboarding_required
@require_http_methods(["POST"])
def submit(request):
    try:
        service.submit_onboarding(request.user)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, "Onboarding submitted for administrator review.")
    return redirect("partner-portal:dashboard")


def file_response(document):
    if not document.file:
        raise Http404
    try:
        response = FileResponse(document.file.open("rb"), as_attachment=True, filename=document.original_name, content_type=document.content_type)
    except FileNotFoundError:
        raise Http404
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    return response


@login_required
@require_http_methods(["GET"])
def document_file(request, pk):
    return file_response(service.accessible_document(request.user, pk))


@manager_required
@require_http_methods(["GET", "POST"])
def review(request, pk):
    partner = get_object_or_404(Partner, pk=pk)
    form = ReviewForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            service.review_onboarding(request.user, pk, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, "Onboarding decision saved.")
            return redirect("partners:onboarding", pk=pk)
    return render(request, "partners/onboarding.html", {"partner": partner, "form": form,
        "profile_form": OnboardingForm(instance=partner), "progress": service.progress(partner),
        "documents": partner.onboarding_documents.filter(deleted_at__isnull=True), "history": partner.onboarding_history.select_related("actor")})


@manager_required
@require_http_methods(["POST"])
def document_review(request, pk):
    doc = service.accessible_document(request.user, pk)
    try:
        service.review_document(request.user, pk, request.POST.get("decision"), request.POST.get("reason", "")[:5000])
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("partners:onboarding", pk=doc.partner_id)
