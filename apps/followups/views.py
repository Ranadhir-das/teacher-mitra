from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.leads.permissions import manageable_leads
from apps.leads.models import Lead

from apps.accounts.models import User
from django.utils import timezone

from .forms import FollowUpCompleteForm, FollowUpForm
from .models import FollowUp
from .permissions import FollowUpPermission, visible_followups, assignee_choices
from .services import (
    cancel_followup,
    complete_followup,
    create_followup,
)


def _check_permission(request):
    permission = FollowUpPermission()

    if not permission.has_permission(request, None):
        raise PermissionDenied


@login_required
@require_http_methods(["GET", "POST"])
def followup_create(request, lead_id):
    _check_permission(request)

    lead = get_object_or_404(
        manageable_leads(request.user),
        pk=lead_id,
    )

    form = FollowUpForm(request.POST or None)
    form.fields["assigned_to"].queryset = assignee_choices(request.user, lead)

    if request.method == "POST" and form.is_valid():
        try:
            followup = create_followup(
                lead=lead,
                assigned_to=form.cleaned_data["assigned_to"],
                created_by=request.user,
                followup_type=form.cleaned_data["followup_type"],
                scheduled_at=form.cleaned_data["scheduled_at"],
                notes=form.cleaned_data["notes"],
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(
                request,
                "Follow-up scheduled successfully.",
            )
            return redirect(
                "leads:detail",
                pk=lead.pk,
            )

    return render(
        request,
        "followups/form.html",
        {
            "form": form,
            "lead": lead,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def followup_complete(request, pk):
    _check_permission(request)

    followup = get_object_or_404(
        visible_followups(request.user).select_related("lead"),
        pk=pk,
    )

    permission = FollowUpPermission()

    if not permission.has_object_permission(
        request,
        None,
        followup,
    ):
        raise PermissionDenied

    form = FollowUpCompleteForm(
        request.POST or None,
        instance=followup,
    )

    if request.method == "POST" and form.is_valid():
        try:
            complete_followup(
                followup=followup,
                actor=request.user,
                outcome=form.cleaned_data["outcome"],
                notes=form.cleaned_data["notes"],
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(
                request,
                "Follow-up completed.",
            )
            return redirect(
                "leads:detail",
                pk=followup.lead_id,
            )

    return render(
        request,
        "followups/complete.html",
        {
            "form": form,
            "followup": followup,
        },
    )


@login_required
@require_http_methods(["POST"])
def followup_cancel(request, pk):
    _check_permission(request)

    followup = get_object_or_404(
        visible_followups(request.user).select_related("lead"),
        pk=pk,
    )

    permission = FollowUpPermission()

    if not permission.has_object_permission(
        request,
        None,
        followup,
    ):
        raise PermissionDenied

    try:
        cancel_followup(
            followup=followup,
            actor=request.user,
        )
    except ValidationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            "Follow-up cancelled.",
        )

    return redirect(
        "leads:detail",
        pk=followup.lead_id,
    )


@login_required
def followup_list(request):
    _check_permission(request)

    followups = (
        visible_followups(request.user)
        .select_related(
            "lead",
            "assigned_to",
            "created_by",
        )
        .order_by(
            "scheduled_at",
            "pk",
        )
    )

    status = request.GET.get("status", "").strip()
    followup_type = request.GET.get("type", "").strip()
    assigned_to = request.GET.get("assigned_to", "").strip()
    quick_filter = request.GET.get("quick", "").strip()

    if status:
        followups = followups.filter(status=status)

    if followup_type:
        followups = followups.filter(
            followup_type=followup_type
        )

    if assigned_to and assigned_to.isdecimal():
        followups = followups.filter(
            assigned_to_id=assigned_to
        )

    today = timezone.localdate()
    now = timezone.now()
    
    if quick_filter == "today":
        followups = followups.filter(
            scheduled_at__date=today,
        )
    
    elif quick_filter == "upcoming":
        followups = followups.filter(
            status=FollowUp.Status.SCHEDULED,
            scheduled_at__gte=now,
        )
    
    elif quick_filter == "missed":
        followups = followups.filter(
            status=FollowUp.Status.MISSED,
        )
    
    elif quick_filter == "completed":
        followups = followups.filter(
            status=FollowUp.Status.COMPLETED,
        )

    users = User.objects.filter(
        is_active=True,
        role__in={
            "SUPER_ADMIN",
            "ADMIN",
            "TEAM_LEADER",
            "COUNSELLOR",
        },
    ).order_by("name")

    return render(
        request,
        "followups/list.html",
        {
            "followups": followups,
            "selected_status": status,
            "selected_type": followup_type,
            "selected_assigned_to": assigned_to,
            "status_choices": FollowUp.Status.choices,
            "type_choices": FollowUp.Type.choices,
            "users": users,
            "quick_filter": quick_filter,
        },
    )