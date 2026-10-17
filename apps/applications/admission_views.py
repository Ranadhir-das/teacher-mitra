from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from .admission_forms import AdmissionForm
from .admissions import ADMISSION_FIELDS, save_admission
from .models import Admission
from .permissions import visible_applications
from .views import check_access


@login_required
@require_http_methods(["GET", "POST"])
def admission_edit(request, application_id=None):
    check_access(request.user)
    application = get_object_or_404(visible_applications(request.user), pk=application_id) if application_id else None
    admission = Admission.objects.filter(application=application).first() if application else None
    initial = {field: getattr(admission, field) for field in ADMISSION_FIELDS} if admission else {"status": "PENDING", "payment_status": "PENDING"}
    form = AdmissionForm(request.POST if request.method == "POST" else None, actor=request.user, application=application, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data.copy()
        selected = data.pop("application")
        try:
            admission = save_admission(request.user, selected.pk, data)
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, "Admission saved.")
            return redirect("applications:detail", pk=admission.application_id)
    return render(request, "applications/admission_form.html", {"form": form, "application": application})
