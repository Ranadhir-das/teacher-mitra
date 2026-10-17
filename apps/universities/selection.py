"""One education selection policy for CRM, partner submissions and applications."""
from django.core.exceptions import ValidationError


def validate_selection(country, university, course, *, previous=(None, None, None), fields=("selected_country", "selected_university", "selected_course")):
    country_field, university_field, course_field = fields
    # Older clients may send only university/course; its country is authoritative.
    if country is None and university is not None:
        country = university.country
    ids = (getattr(country, "pk", None), getattr(university, "pk", None), getattr(course, "pk", None))
    if university and (not country or university.country_id != country.pk):
        raise ValidationError({university_field: "Selected university does not belong to the selected country."})
    if course and (not university or course.university_id != university.pk):
        raise ValidationError({course_field: "Selected course does not belong to the selected university."})
    if ids != previous:
        if country and not country.is_active:
            raise ValidationError({country_field: "Choose an active country."})
        if university and not university.is_active:
            raise ValidationError({university_field: "Choose an active university."})
        if course and (not course.is_active or course.intake_status == "CLOSED"):
            raise ValidationError({course_field: "Choose an active course with an open or upcoming intake."})
    return country
