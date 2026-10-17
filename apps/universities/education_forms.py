from django import forms
from django.db.models import Q
from .models import Country, University
from apps.courses.models import Course


class EducationFormMixin:
    education_fields = ("selected_country", "selected_university", "selected_course")

    class Media:
        js = ("js/education.js",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        country_name, university_name, course_name = self.education_fields
        university_id = getattr(self.instance, university_name + "_id", None)
        course_id = getattr(self.instance, course_name + "_id", None) if course_name else None
        saved_country = getattr(self.instance, country_name + "_id", None)
        if not saved_country and university_id:
            saved_country = University.objects.filter(pk=university_id).values_list("country_id", flat=True).first()
        if country_name not in self.fields:
            self.fields[country_name] = forms.ModelChoiceField(Country.objects.all(), required=True)
        self.initial.setdefault(country_name, saved_country)
        def selected(name):
            value = self.data.get(self.add_prefix(name)) if self.is_bound else self.initial.get(name)
            return getattr(value, "pk", value)
        university = selected(university_name)
        country = selected(country_name)
        # Preserve old web clients that did not yet send a country control.
        if not country and university and str(university).isdecimal() and (not self.is_bound or self.add_prefix(country_name) not in self.data):
            country = University.objects.filter(pk=university).values_list("country_id", flat=True).first()
            self.initial[country_name] = country
            if self.is_bound:
                self.data = self.data.copy()
                self.data[self.add_prefix(country_name)] = country or ""
        self.fields[university_name].label_from_instance = lambda university: f"{university.name} ({university.country.name})"
        self.fields[country_name].queryset = Country.objects.filter(Q(is_active=True) | Q(pk=saved_country))
        universities = University.objects.select_related("country").filter(Q(is_active=True, country__is_active=True) | Q(pk=university_id))
        self.fields[university_name].queryset = universities.filter(country_id=country) if country and str(country).isdecimal() else universities.none()
        if course_name:
            courses = Course.objects.select_related("university", "university__country").filter(
                Q(is_active=True, university__is_active=True, university__country__is_active=True, intake_status__in=["OPEN", "UPCOMING"]) | Q(pk=course_id))
            self.fields[course_name].queryset = courses.filter(university_id=university) if university and str(university).isdecimal() else courses.none()
        for name, level in ((country_name, "country"), (university_name, "university"), (course_name, "course")):
            if name:
                self.fields[name].widget.attrs["data-education"] = level
        # Add the non-model Country selector before its dependants.
        names = list(self.fields)
        names.remove(country_name)
        names.insert(names.index(university_name), country_name)
        self.order_fields(names)
