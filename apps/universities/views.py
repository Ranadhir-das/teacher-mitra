from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from apps.accounts.permissions import is_internal_user, can_manage_employees
from .models import Country, University
from apps.courses.models import Course
from .forms import CountryForm, UniversityForm, CourseForm


def config(kind):
    if kind == "country":
        return Country, CountryForm, "countries", "Country"
    return (Course, CourseForm, "courses", "Course") if kind == "course" else (University, UniversityForm, "universities", "University")


def authorize(user, write=False):
    if not (can_manage_employees(user) if write else is_internal_user(user)):
        raise PermissionDenied


@login_required
def index(request, kind):
    authorize(request.user)
    model, form, namespace, label = config(kind)
    qs = model.objects.all()
    search = request.GET.get("search", "").strip()[:200]
    if search:
        query = Q(name__icontains=search)
        if kind == "country":
            query |= Q(code__icontains=search)
        if kind == "university":
            query |= Q(country__name__icontains=search)
        if kind == "course":
            query |= Q(university__country__name__icontains=search) | Q(program__icontains=search) | Q(university__name__icontains=search)
        qs = qs.filter(query)
    status = request.GET.get("status", "")
    if status in ("active", "inactive"):
        qs = qs.filter(is_active=status == "active")
    if kind in ("university", "course"):
        country = request.GET.get("country", "")
        if country:
            lookup = "country_id" if kind == "university" else "university__country_id"
            qs = qs.filter(**{lookup: country}) if country.isdecimal() else qs.none()
    if kind == "university":
        qs = qs.select_related("country")
    if kind == "course":
        qs = qs.select_related("university__country")
        university = request.GET.get("university", "")
        if university:
            qs = qs.filter(university_id=university) if university.isdecimal() else qs.none()
        mode = request.GET.get("mode", "")
        intake_status = request.GET.get("intake_status", "")
        if mode:
            qs = qs.filter(mode=mode)
        if intake_status:
            qs = qs.filter(intake_status=intake_status)
    query = request.GET.copy()
    query.pop("page", None)
    return render(request, "catalogue/list.html", {"page_obj": Paginator(qs, 20).get_page(request.GET.get("page")),
        "namespace": namespace, "label": label, "kind": kind, "query": query.urlencode(),
        "countries": Country.objects.all(), "universities": University.objects.all(), "modes": Course.Mode.choices, "intakes": Course.IntakeStatus.choices})


@login_required
def detail(request, kind, pk):
    authorize(request.user)
    model, form, namespace, label = config(kind)
    obj = get_object_or_404(model, pk=pk)
    values = [(obj._meta.get_field(name).verbose_name, getattr(obj, f"get_{name}_display")() if obj._meta.get_field(name).choices else getattr(obj, name)) for name in form.Meta.fields]
    if kind == "course":
        values.insert(0, ("Country", obj.university.country))
    return render(request, "catalogue/detail.html", {"object": obj, "values": values, "namespace": namespace, "label": label, "kind": kind})


@login_required
@require_http_methods(["GET", "POST"])
def edit(request, kind, pk=None):
    authorize(request.user, write=True)
    model, form_class, namespace, label = config(kind)
    obj = get_object_or_404(model, pk=pk) if pk else None
    form = form_class(request.POST if request.method == "POST" else None, instance=obj)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                obj = form.save()
        except IntegrityError:
            form.add_error(None, "This catalogue entry already exists. Review the name, mode and intake.")
        else:
            messages.success(request, f"{label} saved.")
            return redirect(namespace + ":detail", pk=obj.pk)
    return render(request, "catalogue/form.html", {"form": form, "object": obj, "namespace": namespace, "label": label})


@login_required
@require_http_methods(["POST"])
def status(request, kind, pk):
    authorize(request.user, write=True)
    model, form, namespace, label = config(kind)
    obj = get_object_or_404(model, pk=pk)
    action = request.POST.get("action")
    if action not in ("activate", "deactivate"):
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest("Invalid action")
    obj.is_active = action == "activate"
    obj.save(update_fields=["is_active", "updated_at"])
    messages.success(request, f"{label} status updated.")
    return redirect(namespace + ":detail", pk=pk)
