from django.db.models import Case, IntegerField, Q, Value, When
from .forms import LeadFilterForm
from .validators import normalize_phone
from django.core.exceptions import ValidationError


def filter_leads(queryset, params, actor):
    form = LeadFilterForm(params, actor=actor)
    if not form.is_valid():
        return queryset.none(), form
    data = form.cleaned_data
    if data.get("partner"):
        queryset = queryset.filter(partner=data["partner"])
    if data.get("search"):
        term = data["search"]
        query = Q(full_name__icontains=term) | Q(phone__icontains=term) | Q(alternate_phone__icontains=term) | Q(email__icontains=term)
        try:
            normalized = normalize_phone(term)
            if normalized:
                query |= Q(phone__icontains=normalized) | Q(alternate_phone__icontains=normalized)
        except ValidationError:
            pass
        queryset = queryset.filter(query)
    for key in ("status", "priority", "lead_source"):
        if data.get(key):
            queryset = queryset.filter(**{key: data[key]})
    if data.get("assigned_to"):
        queryset = queryset.filter(assigned_counsellor=data["assigned_to"])
    for key in ("city", "state"):
        if data.get(key):
            queryset = queryset.filter(**{key + "__iexact": data[key]})
    if data.get("created_from"):
        queryset = queryset.filter(created_at__date__gte=data["created_from"])
    if data.get("created_to"):
        queryset = queryset.filter(created_at__date__lte=data["created_to"])
    activity = data.get("activity") or "active"
    if activity != "all":
        queryset = queryset.filter(is_active=activity == "active")
    ordering = {"newest": "-created_at", "oldest": "created_at", "name": "full_name", "updated": "-updated_at"}
    if data.get("sort") == "priority":
        queryset = queryset.annotate(priority_order=Case(
            When(priority="URGENT", then=Value(0)), When(priority="HIGH", then=Value(1)),
            When(priority="MEDIUM", then=Value(2)), default=Value(3), output_field=IntegerField(),
        )).order_by("priority_order", "-created_at", "-pk")
    else:
        queryset = queryset.order_by(ordering.get(data.get("sort"), "-created_at"), "-pk")
    return queryset, form
