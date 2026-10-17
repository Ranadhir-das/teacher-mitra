import re
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from django.utils import timezone


def normalize_phone(value):
    value = (value or "").strip()
    if not value:
        return ""
    if not re.fullmatch(r"[+0-9() .-]+", value):
        raise ValidationError("Use digits and standard phone punctuation only.")
    digits = re.sub(r"[^0-9]", "", value)
    if not 7 <= len(digits) <= 15:
        raise ValidationError("Enter a phone number with 7 to 15 digits, including country code if used.")
    return digits


def validate_phone(value):
    normalize_phone(value)


def validate_year(value):
    if value < 1950 or value > timezone.localdate().year + 1:
        raise ValidationError("Passing year must be between 1950 and next year.")


def validate_score(value):
    if not value:
        return
    # A bare value is a percentage; CGPA uses an explicit denominator, e.g. 8.5/10 or 3.4/4.
    try:
        parts = value.strip().rstrip("%").split("/")
        if len(parts) not in (1, 2):
            raise ValueError
        score = Decimal(parts[0])
        maximum = Decimal(parts[1]) if len(parts) == 2 else Decimal(100)
        if not score.is_finite() or not maximum.is_finite() or maximum <= 0 or maximum > 100 or not 0 <= score <= maximum:
            raise ValueError
    except (InvalidOperation, ValueError):
        raise ValidationError("Enter 0-100 for percentage, or CGPA with its scale (e.g. 8.5/10).")
