import secrets
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from apps.leads.validators import normalize_phone, validate_phone


def generate_partner_code():
    # 48 random bits, independent of sequential database identifiers.
    return "ALP-P" + secrets.token_hex(6).upper()


class Partner(models.Model):
    class Type(models.TextChoices):
        INDIVIDUAL = "INDIVIDUAL", "Individual"
        EDUCATION_CONSULTANCY = "EDUCATION_CONSULTANCY", "Education consultancy"
        COACHING_CENTER = "COACHING_CENTER", "Coaching center"
        REFERRAL_AGENT = "REFERRAL_AGENT", "Referral agent"
        CORPORATE = "CORPORATE", "Corporate"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACTIVE = "ACTIVE", "Approved"
        REGISTERED = "REGISTERED", "Registered"
        ONBOARDING = "ONBOARDING", "Onboarding"
        SUBMITTED = "SUBMITTED", "Submitted for review"
        CHANGES_REQUIRED = "CHANGES_REQUIRED", "Changes required"
        REJECTED = "REJECTED", "Rejected"
        SUSPENDED = "SUSPENDED", "Suspended"
        INACTIVE = "INACTIVE", "Inactive"

    partner_code = models.CharField(max_length=32, unique=True, default=generate_partner_code,
        validators=[RegexValidator(r"^ALP-P[A-Z0-9]{3,24}$", "Use ALP-P followed by 3-24 uppercase letters or digits.")])
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="partner_profile")
    business_name = models.CharField(max_length=200, db_index=True)
    contact_person = models.CharField(max_length=150)
    email = models.EmailField(db_index=True)
    phone = models.CharField(max_length=20, validators=[validate_phone], db_index=True)
    alternate_phone = models.CharField(max_length=20, blank=True, validators=[validate_phone])
    partner_type = models.CharField(max_length=24, choices=Type.choices, default=Type.INDIVIDUAL, db_index=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    pincode = models.CharField(max_length=12, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    tax_type = models.CharField(max_length=16, choices=[("PAN", "PAN"), ("GST", "GST"), ("NOT_APPLICABLE", "Not applicable")], blank=True)
    tax_identifier = models.CharField(max_length=32, blank=True)
    tax_explanation = models.TextField(blank=True, max_length=2000)
    review_feedback = models.TextField(blank=True, max_length=5000)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="partner_reviews")
    notes = models.TextField(blank=True, help_text="Internal notes. Never shared with the partner.")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_partners")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [models.CheckConstraint(condition=models.Q(status__in=["PENDING", "ACTIVE", "SUSPENDED", "INACTIVE", "REJECTED", "REGISTERED", "ONBOARDING", "SUBMITTED", "CHANGES_REQUIRED"]), name="partners_valid_status")]

    def clean(self):
        self.partner_code = self.partner_code.strip().upper()
        self.email = self.email.strip().lower()
        for name in ("business_name", "contact_person"):
            value = getattr(self, name).strip()
            if not value:
                raise ValidationError({name: "This field is required."})
            setattr(self, name, value)
        for name in ("phone", "alternate_phone"):
            try:
                setattr(self, name, normalize_phone(getattr(self, name)))
            except ValidationError as exc:
                raise ValidationError({name: exc.messages})
        if self.user_id and (self.user.role != "PARTNER" or self.user.is_staff or self.user.is_superuser):
            raise ValidationError({"user": "A partner login must have PARTNER role and no staff or superuser access."})
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values("partner_code", "user_id").first()
            if previous and (self.partner_code != previous["partner_code"] or (previous["user_id"] and self.user_id != previous["user_id"])):
                raise ValidationError("Partner code and existing account linkage cannot be changed.")

    def __str__(self):
        return f"{self.business_name} ({self.partner_code})"


class PartnerOnboardingHistory(models.Model):
    partner = models.ForeignKey(Partner, on_delete=models.PROTECT, related_name="onboarding_history")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=32)
    previous_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
