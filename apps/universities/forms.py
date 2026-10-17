from django import forms
from .models import Country, University
from apps.courses.models import Course


class UniversityForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        from django.db.models import Q
        super().__init__(*args, **kwargs)
        self.fields["country"].queryset = Country.objects.filter(Q(is_active=True) | Q(pk=self.instance.country_id))

    class Meta:
        model = University
        fields = ["name", "country", "website", "description", "is_active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


from .education_forms import EducationFormMixin


class CourseForm(EducationFormMixin, forms.ModelForm):
    education_fields = ("country", "university", None)
    country = forms.ModelChoiceField(queryset=Country.objects.all())
    class Meta:
        model = Course
        fields = ["university", "name", "program", "duration_months", "fees", "currency", "eligibility", "mode", "intake", "intake_status", "is_active"]
        widgets = {"eligibility": forms.Textarea(attrs={"rows": 3})}


class CountryForm(forms.ModelForm):
    class Meta:
        model = Country
        fields = ["name", "code", "is_active"]
