from django import forms
from django.db.models import Q
from .models import Application
from .permissions import application_leads
from .services import EDITABLE_FIELDS, validate_workflow


from apps.universities.education_forms import EducationFormMixin


class ApplicationForm(EducationFormMixin, forms.ModelForm):
    education_fields = ("country", "university", "course")
    country = forms.ModelChoiceField(queryset=None, required=True)
    class Meta:
        model = Application
        fields = ("lead",) + EDITABLE_FIELDS
        widgets = {"submission_date": forms.DateInput(attrs={"type": "date"}),
                   "academic_details": forms.Textarea(attrs={"rows": 5}),
                   "remarks": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lead"].queryset = application_leads(actor).filter(is_active=True)
        if self.instance.pk:
            self.fields["lead"].queryset = application_leads(actor)
            self.fields["lead"].disabled = True
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-select" if isinstance(field.widget, forms.Select) else "form-control")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("lead") and cleaned.get("status"):
            candidate = Application(lead=cleaned["lead"], status=cleaned["status"])
            old = Application.objects.get(pk=self.instance.pk) if self.instance.pk else None
            validate_workflow(candidate, old)
        return cleaned
