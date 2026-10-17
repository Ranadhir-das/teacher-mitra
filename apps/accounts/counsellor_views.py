from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from .permissions import can_manage_employees
from .counsellor_permissions import visible_counsellors, can_edit_counsellor
from .counsellor_forms import CounsellorPasswordForm
from .counsellor_services import reset_counsellor_password


@login_required
@require_http_methods(["GET", "POST"])
def counsellor_password(request, pk):
    if not can_manage_employees(request.user):
        raise PermissionDenied
    target = get_object_or_404(visible_counsellors(request.user), pk=pk)
    if not can_edit_counsellor(request.user, target):
        raise PermissionDenied
    form = CounsellorPasswordForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            reset_counsellor_password(request.user, pk, form.cleaned_data["password1"])
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, "Password changed. Existing counsellor sessions are invalidated.")
            return redirect("accounts:employee-detail", pk=pk)
    return render(request, "accounts/counsellor_password.html", {"form": form, "counsellor": target})
