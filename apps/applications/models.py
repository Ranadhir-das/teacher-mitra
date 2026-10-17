from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Application(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        STARTED = "STARTED", "Started"
        SUBMITTED = "SUBMITTED", "Submitted"
        UNDER_REVIEW = "UNDER_REVIEW", "Under review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    lead = models.ForeignKey("leads.Lead", on_delete=models.PROTECT, related_name="applications")
    university = models.ForeignKey("universities.University", on_delete=models.PROTECT, related_name="applications")
    course = models.ForeignKey("courses.Course", on_delete=models.PROTECT, related_name="applications")
    reference = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    submission_date = models.DateField(null=True, blank=True)
    academic_details = models.TextField(blank=True, max_length=20000)
    remarks = models.TextField(blank=True, max_length=10000)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_applications")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="updated_applications")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [models.CheckConstraint(condition=models.Q(status__in=["DRAFT", "STARTED", "SUBMITTED", "UNDER_REVIEW", "APPROVED", "REJECTED", "CANCELLED"]), name="application_valid_status")]

    def clean(self):
        old = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        if old and old.lead_id != self.lead_id:
            raise ValidationError({"lead": "An application cannot be moved to another lead."})
        if self.course_id and self.course.university_id != self.university_id:
            raise ValidationError({"course": "Select a course belonging to the selected university."})
        from apps.universities.selection import validate_selection
        validate_selection(self.university.country if self.university_id else None,
            self.university if self.university_id else None, self.course if self.course_id else None,
            previous=(old.university.country_id, old.university_id, old.course_id) if old else (None, None, None),
            fields=("university", "university", "course"))
        if not old or (old.course_id, old.university_id) != (self.course_id, self.university_id):
            if self.university_id and not self.university.is_active:
                raise ValidationError({"university": "Choose an active university."})
            if self.course_id and (not self.course.is_active or self.course.intake_status == "CLOSED"):
                raise ValidationError({"course": "Choose an active course with an open or upcoming intake."})
            if old and old.status not in (self.Status.DRAFT, self.Status.STARTED):
                raise ValidationError({"course": "The offering cannot change after submission."})
        if self.submission_date and self.submission_date > timezone.localdate():
            raise ValidationError({"submission_date": "Submission date cannot be in the future."})
        if self.status in (self.Status.DRAFT, self.Status.STARTED) and self.submission_date:
            raise ValidationError({"submission_date": "Only submitted applications have a submission date."})

    def __str__(self):
        return self.reference or f"Application #{self.pk}"


class ApplicationStatusHistory(models.Model):
    """Append-only audit events include field edits as well as status changes."""
    application = models.ForeignKey(Application, on_delete=models.PROTECT, related_name="history")
    previous_status = models.CharField(max_length=20, choices=Application.Status.choices, blank=True)
    new_status = models.CharField(max_length=20, choices=Application.Status.choices)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    changed_at = models.DateTimeField(auto_now_add=True)
    changes = models.JSONField(default=dict)

    class Meta:
        ordering = ["changed_at", "pk"]


class Admission(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        CONFIRMED = "CONFIRMED", "Confirmed"
        CANCELLED = "CANCELLED", "Cancelled"

    class PaymentStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PARTIAL = "PARTIAL", "Partially paid"
        PAID = "PAID", "Paid"
        WAIVED = "WAIVED", "Waived"
        REFUNDED = "REFUNDED", "Refunded"

    application = models.OneToOneField(Application, on_delete=models.PROTECT, related_name="admission")
    lead = models.ForeignKey("leads.Lead", on_delete=models.PROTECT, related_name="admissions")
    university = models.ForeignKey("universities.University", on_delete=models.PROTECT, related_name="admissions")
    course = models.ForeignKey("courses.Course", on_delete=models.PROTECT, related_name="admissions")
    enrollment_number = models.CharField(max_length=120, blank=True)
    admission_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    payment_status = models.CharField(max_length=12, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    remarks = models.TextField(blank=True, max_length=10000)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="confirmed_admissions")
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_admissions")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="updated_admissions")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=["PENDING", "CONFIRMED", "CANCELLED"]), name="admission_valid_status"),
            models.CheckConstraint(condition=models.Q(payment_status__in=["PENDING", "PARTIAL", "PAID", "WAIVED", "REFUNDED"]), name="admission_valid_payment_status"),
        ]

    def clean(self):
        if self.application_id:
            app = self.application
            if (self.lead_id, self.university_id, self.course_id) != (app.lead_id, app.university_id, app.course_id):
                raise ValidationError("Admission lead, university and course must match its application.")
        if self.admission_date and self.admission_date > timezone.localdate():
            raise ValidationError({"admission_date": "Admission date cannot be in the future."})
        if self.status == self.Status.CONFIRMED and (not self.enrollment_number.strip() or not self.admission_date):
            raise ValidationError("Confirmation requires an enrollment number and admission date.")

    def __str__(self):
        return self.enrollment_number or f"Admission for application #{self.application_id}"


class AdmissionHistory(models.Model):
    admission = models.ForeignKey(Admission, on_delete=models.PROTECT, related_name="history")
    previous_status = models.CharField(max_length=12, choices=Admission.Status.choices, blank=True)
    new_status = models.CharField(max_length=12, choices=Admission.Status.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    changes = models.JSONField(default=dict)

    class Meta:
        ordering = ["created_at", "pk"]
