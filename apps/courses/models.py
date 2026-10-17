from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError


class Course(models.Model):
    class Mode(models.TextChoices):
        ONLINE = "ONLINE", "Online"
        DISTANCE = "DISTANCE", "Distance"
        ON_CAMPUS = "ON_CAMPUS", "On campus"
        HYBRID = "HYBRID", "Hybrid"

    class IntakeStatus(models.TextChoices):
        OPEN = "OPEN", "Open"
        UPCOMING = "UPCOMING", "Upcoming"
        CLOSED = "CLOSED", "Closed"

    university = models.ForeignKey("universities.University", on_delete=models.PROTECT, related_name="courses")
    name = models.CharField(max_length=200)
    program = models.CharField(max_length=120, verbose_name="Degree / program")
    duration_months = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    fees = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)], help_text="Total course tuition; currency specified below.")
    currency = models.CharField(max_length=3, default="INR")
    eligibility = models.TextField()
    mode = models.CharField(max_length=16, choices=Mode.choices)
    intake = models.CharField(max_length=120, help_text="For example: July 2027")
    intake_status = models.CharField(max_length=12, choices=IntakeStatus.choices, default=IntakeStatus.OPEN)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["university__name", "name", "pk"]
        constraints = [
            models.CheckConstraint(condition=models.Q(fees__gte=0), name="course_nonnegative_fees"),
            models.CheckConstraint(condition=models.Q(duration_months__gte=1), name="course_positive_duration"),
            models.UniqueConstraint(fields=["university", "name", "mode", "intake"], name="course_unique_offering"),
        ]

    def clean(self):
        old = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        if self.university_id and (not old or old.university_id != self.university_id):
            if not self.university.is_active or not self.university.country.is_active:
                raise ValidationError({"university": "Choose a university in an active country."})
        self.currency = self.currency.strip().upper()
        if len(self.currency) != 3 or not self.currency.isascii() or not self.currency.isalpha():
            raise ValidationError({"currency": "Use a three-letter currency code, e.g. INR."})
        if self.pk and type(self).objects.filter(pk=self.pk).exclude(university_id=self.university_id).exists() and (self.selected_leads.exists() or self.applications.exists()):
            raise ValidationError({"university": "An offering selected by leads or applications cannot be moved to another university."})

    def __str__(self):
        return f"{self.name} - {self.university} ({self.get_mode_display()}, {self.intake})"
