from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from apps.applications.permissions import visible_applications
from apps.applications.views import check_access
from .forms import DocumentForm, DocumentActionForm
from .services import create_document, update_document, visible_documents


@login_required
@require_http_methods(["GET", "POST"])
def document_create(request, application_id=None):
    check_access(request.user)
    application = get_object_or_404(visible_applications(request.user), pk=application_id) if application_id else None
    form = DocumentForm(request.POST if request.method == "POST" else None, request.FILES or None,
        actor=request.user, application=application)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data.copy()
        selected = data.pop("application")
        try:
            document = create_document(request.user, selected.pk, **data)
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, "Document saved.")
            return redirect("documents:detail", pk=document.pk)
    return render(request, "documents/form.html", {"form": form, "application": application})


@login_required
@require_http_methods(["GET", "POST"])
def document_detail(request, pk):
    check_access(request.user)
    document = get_object_or_404(visible_documents(request.user).select_related("application", "lead", "reviewed_by"), pk=pk)
    form = DocumentActionForm(request.POST if request.method == "POST" else None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            document = update_document(request.user, pk, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, "Document updated.")
            return redirect("documents:detail", pk=pk)
    return render(request, "documents/detail.html", {"document": document, "form": form,
        "history": document.history.select_related("actor")})


@login_required
@require_http_methods(["GET"])
def document_file(request, pk, download=False):
    check_access(request.user)
    document = get_object_or_404(visible_documents(request.user), pk=pk, deleted_at__isnull=True)
    if not document.file:
        raise Http404("No file has been submitted.")
    try:
        stream = document.file.open("rb")
    except FileNotFoundError as exc:
        raise Http404("The file is unavailable.") from exc
    response = FileResponse(stream, as_attachment=download, filename=document.original_name, content_type=document.content_type)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    return response
