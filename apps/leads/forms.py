from django import forms
from django.core.exceptions import ValidationError
from .models import Lead, Tag
from .permissions import assignment_choices, permitted_teams, is_admin
from .services import EDITABLE_FIELDS
from .workflow import allowed_statuses

SECTIONS = [
    ("Personal information", ("full_name", "phone", "alternate_phone", "email", "date_of_birth", "gender", "address", "city", "state", "pincode")),
    ("Education", ("highest_qualification", "institution_name", "passing_year", "percentage_or_cgpa", "specialization")),
    ("Course requirement", ("selected_country", "selected_university", "selected_course", "desired_course", "desired_specialization", "preferred_university", "preferred_study_mode", "budget", "career_goal", "additional_requirements")),
    ("Lead information", ("lead_source", "partner", "priority", "assigned_counsellor", "assigned_team")),
    ("Additional information", ("tags", "general_notes", "confirm_duplicate")),
]


from apps.universities.education_forms import EducationFormMixin


class LeadForm(EducationFormMixin, forms.ModelForm):
    confirm_duplicate = forms.BooleanField(required=False, label="I reviewed the possible duplicate and want to keep a separate record")

    class Meta:
        model = Lead
        fields = (*EDITABLE_FIELDS, "tags")
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"}),
                   **{field: forms.Textarea(attrs={"rows": 3}) for field in ("address", "career_goal", "additional_requirements", "general_notes")}}

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        if not is_admin(actor):
            self.fields.pop("partner", None)
        if not self.instance.pk:
            self.fields["assigned_counsellor"] = forms.ModelChoiceField(assignment_choices(actor), required=False)
            self.fields["assigned_team"] = forms.ModelChoiceField(permitted_teams(actor), required=not is_admin(actor))
        if not is_admin(actor) and actor.role != "TEAM_LEADER":
            self.fields.pop("confirm_duplicate")

    @property
    def sections(self):
        return [(title, [self[field] for field in fields if field in self.fields]) for title, fields in SECTIONS]


class AssignmentForm(forms.Form):
    assigned_counsellor = forms.ModelChoiceField(queryset=None, required=False, empty_label="Unassigned")
    assigned_team = forms.ModelChoiceField(queryset=None, required=False, empty_label="No team")
    reason = forms.CharField(required=False, max_length=2000, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_counsellor"].queryset = assignment_choices(actor)
        self.fields["assigned_team"].queryset = permitted_teams(actor) if actor.role != "COUNSELLOR" else actor.crm_teams.filter(is_active=True)


class StatusForm(forms.Form):
    status = forms.ChoiceField(choices=Lead.Status.choices)
    note = forms.CharField(required=False, max_length=2000, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, actor, lead, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = allowed_statuses(actor, lead)


class NoteForm(forms.Form):
    note = forms.CharField(max_length=10000, widget=forms.Textarea(attrs={"rows": 5}))


class ArchiveForm(forms.Form):
    action = forms.ChoiceField(choices=[("archive", "Archive"), ("restore", "Restore")], widget=forms.HiddenInput)


class BulkForm(AssignmentForm):
    ids = forms.CharField(widget=forms.HiddenInput)
    operation = forms.ChoiceField(choices=[("assign", "Assign leads"), ("status", "Change status")])
    status = forms.ChoiceField(choices=[("", "Choose status"), *Lead.Status.choices], required=False)
    note = forms.CharField(required=False, max_length=2000, widget=forms.Textarea(attrs={"rows": 3}))

    def clean_ids(self):
        try:
            ids = sorted(set(int(value) for value in self.cleaned_data["ids"].split(",")))
        except ValueError:
            raise ValidationError("Invalid lead selection.")
        if not ids or len(ids) > 100 or min(ids) < 1:
            raise ValidationError("Select between 1 and 100 leads.")
        return ids

    def clean(self):
        data = super().clean()
        if data.get("operation") == "status" and not data.get("status"):
            self.add_error("status", "Choose a status.")
        return data


class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ["name"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip().upper()
        if Tag.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise ValidationError("This tag already exists.")
        return name


class LeadFilterForm(forms.Form):
    partner = forms.ModelChoiceField(queryset=None, to_field_name="partner_code", required=False, empty_label="All partners")
    search = forms.CharField(
        required=False,
        max_length=200,
        label="Search",
        widget=forms.SearchInput(attrs={"placeholder": "Name, phone or email", "autocomplete": "off"}),
    )
    status = forms.ChoiceField(choices=[("", "All statuses"), *Lead.Status.choices], required=False)
    priority = forms.ChoiceField(choices=[("", "All priorities"), *Lead.Priority.choices], required=False)
    assigned_to = forms.ModelChoiceField(queryset=None, required=False, label="Counsellor", empty_label="All counsellors")
    lead_source = forms.ChoiceField(choices=[("", "All sources"), *Lead.Source.choices], required=False)
    created_from = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    created_to = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    city = forms.CharField(required=False, max_length=100)
    state = forms.CharField(required=False, max_length=100)
    activity = forms.ChoiceField(choices=[("active", "Active"), ("archived", "Archived"), ("all", "Active and archived")], required=False)
    sort = forms.ChoiceField(choices=[("newest", "Newest"), ("oldest", "Oldest"), ("name", "Name"), ("priority", "Priority"), ("updated", "Last updated")], required=False)
    page_size = forms.TypedChoiceField(choices=[(20, "20 per page"), (50, "50 per page"), (100, "100 per page")], coerce=int, required=False)

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.accounts.models import User
        from apps.partners.models import Partner
        from .permissions import visible_leads
        self.fields["partner"].queryset = Partner.objects.all() if is_admin(actor) else Partner.objects.filter(leads__in=visible_leads(actor)).distinct()
        users = User.objects.filter(role=User.Role.COUNSELLOR)
        if not is_admin(actor):
            users = users.filter(crm_teams__in=permitted_teams(actor)).distinct() if actor.role == User.Role.TEAM_LEADER else users.filter(pk=actor.pk)
        self.fields["assigned_to"].queryset = users

    def clean(self):
        data = super().clean()
        if data.get("created_from") and data.get("created_to") and data["created_from"] > data["created_to"]:
            raise ValidationError("Start date must be before or equal to end date.")
        return data
