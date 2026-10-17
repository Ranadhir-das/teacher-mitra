from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError
from .selection import validate_selection


class LeadEducationValidationMixin:
    def validate(self, attrs):
        attrs = super().validate(attrs)
        fields = ("selected_country", "selected_university", "selected_course")
        values = [attrs.get(field, getattr(self.instance, field, None)) for field in fields]
        if "selected_university" in attrs and "selected_country" not in attrs:
            values[0] = attrs["selected_university"].country if attrs["selected_university"] else None
        previous = tuple(getattr(self.instance, field + "_id", None) for field in fields)
        try:
            country = validate_selection(*values, previous=previous)
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict)
        if any(field in attrs for field in fields):
            attrs["selected_country"] = country
        return attrs
