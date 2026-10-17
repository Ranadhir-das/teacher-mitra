from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from . import services
from .filters import filter_leads
from .forms import LeadForm, AssignmentForm, StatusForm, NoteForm, ArchiveForm, BulkForm, TagForm, SECTIONS
from .models import Lead, Tag
from .permissions import manageable_leads, visible_leads, optimized, can_create, can_assign, can_archive, is_admin

from apps.followups.models import FollowUp
from .activity import build_lead_activity


def get_lead(actor, pk):
    return get_object_or_404(optimized(visible_leads(actor)), pk=pk)


def form_error(form, exc):
    if isinstance(exc, services.DuplicateLeadError):
        form.duplicate_matches = exc.matches
    if hasattr(exc, "message_dict"):
        for field, errors in exc.message_dict.items():
            form.add_error(field if field in form.fields else None, errors)
    else:
        form.add_error(None, exc)


@login_required
def lead_list(request, students=False):
    queryset = visible_leads(request.user)
    if students:
        queryset = queryset.filter(status=Lead.Status.ADMISSION_CONFIRMED)
    queryset, form = filter_leads(queryset, request.GET, request.user)
    page_size = form.cleaned_data.get("page_size") or 20
    page = Paginator(optimized(queryset), page_size).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return render(request, "leads/list.html", {"page_obj": page, "filter_form": form, "query": query.urlencode(),
        "students": students, "can_create": can_create(request.user), "can_assign": can_assign(request.user), "is_admin": is_admin(request.user)})


@login_required
def lead_detail(request, pk):
    lead = get_lead(request.user, pk)

    sections = []

    for title, fields in SECTIONS[:3]:
        values = []

        for name in fields:
            field = lead._meta.get_field(name)

            value = (
                getattr(lead, f"get_{name}_display")()
                if field.choices
                else getattr(lead, name)
            )

            values.append(
                (
                    field.verbose_name.replace("_", " ").title(),
                    value,
                )
            )

        sections.append(
            (
                title,
                values,
            )
        )

    from apps.followups.models import FollowUp

    followups = (
        FollowUp.objects
        .filter(lead=lead)
        .select_related(
            "assigned_to",
            "created_by",
        )
        .order_by("-scheduled_at", "-pk")
    )

    upcoming_followups = followups.filter(
        status=FollowUp.Status.SCHEDULED
    )

    activity = build_lead_activity(
        lead=lead,
        notes=lead.notes.select_related("created_by"),
        status_history=lead.status_history.select_related(
            "changed_by"
        ),
        assignment_history=lead.assignment_history.select_related(
            "previous_counsellor",
            "new_counsellor",
            "assigned_by",
            "previous_team",
            "new_team",
        ),
        followups=followups,
    )

    return render(
        request,
        "leads/detail.html",
        {
            "lead": lead,
            "sections": sections,

            "notes": lead.notes.select_related(
                "created_by"
            ),

            "status_history": lead.status_history.select_related(
                "changed_by"
            ),

            "assignment_history": lead.assignment_history.select_related(
                "previous_counsellor",
                "new_counsellor",
                "assigned_by",
                "previous_team",
                "new_team",
            ),

            "followups": followups,
            "upcoming_followups": upcoming_followups,

            "activity": activity,

            "can_manage_lead": manageable_leads(request.user).filter(pk=lead.pk).exists(),
            "can_assign": can_assign(request.user),
            "can_archive": can_archive(request.user),
        },
    )

@login_required
@require_http_methods(["GET", "POST"])
def lead_edit(request, pk=None):
    lead = get_lead(request.user, pk) if pk else None
    if lead and not lead.is_active:
        raise PermissionDenied("Restore the archived lead before editing.")
    if not lead and not can_create(request.user):
        raise PermissionDenied
    form = LeadForm(request.POST or None, instance=lead, actor=request.user)
    if request.method == "POST" and form.is_valid():
        data = {key: form.cleaned_data[key] for key in services.EDITABLE_FIELDS if key in form.cleaned_data}
        try:
            if lead:
                result = services.update_lead(request.user, lead.pk, data, tags=form.cleaned_data["tags"], confirm_duplicate=form.cleaned_data.get("confirm_duplicate", False))
            else:
                result = services.create_lead(request.user, data, tags=form.cleaned_data["tags"],
                    counsellor=form.cleaned_data.get("assigned_counsellor"), team=form.cleaned_data.get("assigned_team"),
                    confirm_duplicate=form.cleaned_data.get("confirm_duplicate", False))
        except ValidationError as exc:
            form_error(form, exc)
        else:
            messages.success(request, "Lead saved successfully.")
            return redirect("leads:detail", pk=result.pk)
    return render(request, "leads/form.html", {"form": form, "lead": lead})


@login_required
@require_http_methods(["GET", "POST"])
def lead_action(request, pk, action):
    lead = get_lead(request.user, pk)
    if action == "assign":
        if not can_assign(request.user):
            raise PermissionDenied
        form = AssignmentForm(request.POST or None, actor=request.user,
            initial={"assigned_counsellor": lead.assigned_counsellor, "assigned_team": lead.assigned_team})
    elif action == "status":
        form = StatusForm(request.POST or None, actor=request.user, lead=lead)
    elif action == "note":
        form = NoteForm(request.POST or None)
    elif action == "archive":
        if not can_archive(request.user):
            raise PermissionDenied
        form = ArchiveForm(request.POST or None, initial={"action": "archive" if lead.is_active else "restore"})
    else:
        raise Http404
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            if action == "assign":
                services.assign_lead(request.user, pk, data["assigned_counsellor"], data["assigned_team"], data["reason"])
            elif action == "status":
                services.change_status(request.user, pk, data["status"], data["note"])
            elif action == "note":
                services.add_note(request.user, pk, data["note"])
            else:
                services.archive_lead(request.user, pk, active=data["action"] == "restore")
        except ValidationError as exc:
            form_error(form, exc)
        else:
            messages.success(request, "Lead updated successfully.")
            return redirect("leads:detail", pk=pk)
    title = {"assign": "Assign lead", "status": "Change status", "note": "Add note", "archive": "Archive lead" if lead.is_active else "Restore lead"}[action]
    return render(request, "leads/action.html", {"form": form, "lead": lead, "title": title, "action": action})


@login_required
@require_http_methods(["POST"])
def bulk_action(request):
    if request.POST.get("confirm") == "yes":
        form = BulkForm(request.POST, actor=request.user)
        if form.is_valid():
            data = form.cleaned_data
            try:
                kwargs = {"counsellor": data["assigned_counsellor"], "team": data["assigned_team"], "reason": data["reason"]} if data["operation"] == "assign" else {"status": data["status"], "note": data["note"]}
                count = services.bulk_update(request.user, data["ids"], data["operation"], **kwargs)
            except ValidationError as exc:
                form_error(form, exc)
            else:
                messages.success(request, f"Bulk action completed for {count} leads.")
                return redirect("leads:list")
        raw_ids = request.POST.get("ids", "")
    else:
        raw_ids = ",".join(request.POST.getlist("selected"))
        form = BulkForm(actor=request.user, initial={"ids": raw_ids, "operation": request.POST.get("operation", "status")})
    try:
        ids = sorted(set(int(value) for value in raw_ids.split(",") if value))
    except ValueError:
        raise Http404
    if not ids or len(ids) > 100:
        messages.error(request, "Select between 1 and 100 leads.")
        return redirect("leads:list")
    selected = list(visible_leads(request.user).filter(pk__in=ids))
    if len(selected) != len(ids):
        raise PermissionDenied
    return render(request, "leads/bulk.html", {"form": form, "selected": selected})


@login_required
@require_http_methods(["GET", "POST"])
def tag_manage(request, pk=None):
    if not is_admin(request.user):
        raise PermissionDenied
    tag = get_object_or_404(Tag, pk=pk) if pk else None
    form = TagForm(request.POST or None, instance=tag)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Tag saved.")
        return redirect("leads:tags")
    return render(request, "leads/tags.html", {"form": form, "tags": Tag.objects.all(), "tag": tag})
