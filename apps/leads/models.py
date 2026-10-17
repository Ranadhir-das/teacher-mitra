from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from .validators import normalize_phone, validate_phone, validate_score, validate_year


class Tag(models.Model):
    name = models.CharField(max_length=40, unique=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(Lower("name"), name="leads_tag_name_ci_unique")]

    def clean(self):
        self.name = self.name.strip().upper()

    def save(self, *args, **kwargs):
        self.name = self.name.strip().upper()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Lead(models.Model):
    class Status(models.TextChoices):
        NEW = "NEW", "New"
        ASSIGNED = "ASSIGNED", "Assigned"
        CONTACTED = "CONTACTED", "Contacted"
        INTERESTED = "INTERESTED", "Interested"
        COUNSELLING = "COUNSELLING", "Counselling"
        COURSE_SELECTED = "COURSE_SELECTED", "Course selected"
        APPLICATION_STARTED = "APPLICATION_STARTED", "Application started"
        APPLICATION_SUBMITTED = "APPLICATION_SUBMITTED", "Application submitted"
        PAYMENT_PENDING = "PAYMENT_PENDING", "Payment pending"
        ADMISSION_CONFIRMED = "ADMISSION_CONFIRMED", "Admission confirmed"
        NOT_INTERESTED = "NOT_INTERESTED", "Not interested"
        WRONG_NUMBER = "WRONG_NUMBER", "Wrong number"
        NO_RESPONSE = "NO_RESPONSE", "No response"
        NOT_ELIGIBLE = "NOT_ELIGIBLE", "Not eligible"
        LOST = "LOST", "Lost"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"
        URGENT = "URGENT", "Urgent"

    class Source(models.TextChoices):
        PARTNER = "PARTNER", "Partner"
        WEBSITE = "WEBSITE", "Website"
        FACEBOOK = "FACEBOOK", "Facebook"
        INSTAGRAM = "INSTAGRAM", "Instagram"
        GOOGLE = "GOOGLE", "Google"
        REFERRAL = "REFERRAL", "Referral"
        WALK_IN = "WALK_IN", "Walk-in"
        ADVERTISEMENT = "ADVERTISEMENT", "Advertisement"
        CALL = "CALL", "Call"
        WHATSAPP = "WHATSAPP", "WhatsApp"
        OTHER = "OTHER", "Other"

    class Gender(models.TextChoices):
        FEMALE = "FEMALE", "Female"
        MALE = "MALE", "Male"
        OTHER = "OTHER", "Other"
        UNDISCLOSED = "UNDISCLOSED", "Prefer not to say"

    class StudyMode(models.TextChoices):
        ONLINE = "ONLINE", "Online"
        DISTANCE = "DISTANCE", "Distance"
        ON_CAMPUS = "ON_CAMPUS", "On campus"
        HYBRID = "HYBRID", "Hybrid"
        UNDECIDED = "UNDECIDED", "Undecided"

    full_name = models.CharField(max_length=180, db_index=True)
    phone = models.CharField(max_length=20, validators=[validate_phone], db_index=True)
    alternate_phone = models.CharField(max_length=20, blank=True, validators=[validate_phone], db_index=True)
    email = models.EmailField(blank=True, db_index=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=16, choices=Gender.choices, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True, db_index=True)
    state = models.CharField(max_length=100, blank=True, db_index=True)
    pincode = models.CharField(max_length=12, blank=True)
    highest_qualification = models.CharField(max_length=150, blank=True)
    institution_name = models.CharField(max_length=200, blank=True)
    passing_year = models.PositiveSmallIntegerField(null=True, blank=True, validators=[validate_year])
    percentage_or_cgpa = models.CharField(max_length=20, blank=True, validators=[validate_score], help_text="Percentage 0-100, or CGPA with scale, e.g. 8.5/10.")
    specialization = models.CharField(max_length=150, blank=True)
    # Preserve these text preferences when adding optional catalogue FKs in a future migration.
    selected_country = models.ForeignKey("universities.Country", null=True, blank=True, on_delete=models.PROTECT, related_name="leads")
    selected_university = models.ForeignKey("universities.University", null=True, blank=True, on_delete=models.PROTECT, related_name="selected_leads")
    selected_course = models.ForeignKey("courses.Course", null=True, blank=True, on_delete=models.PROTECT, related_name="selected_leads")
    desired_course = models.CharField(max_length=180, blank=True)
    desired_specialization = models.CharField(max_length=180, blank=True)
    preferred_university = models.CharField(max_length=200, blank=True)
    preferred_study_mode = models.CharField(max_length=16, choices=StudyMode.choices, default=StudyMode.UNDECIDED)
    budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    career_goal = models.TextField(blank=True)
    additional_requirements = models.TextField(blank=True)
    lead_source = models.CharField(max_length=20, choices=Source.choices, default=Source.OTHER, db_index=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.NEW, db_index=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM, db_index=True)
    assigned_counsellor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="assigned_leads")
    assigned_team = models.ForeignKey("accounts.Team", null=True, blank=True, on_delete=models.PROTECT, related_name="leads")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_leads")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="updated_leads")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    last_contacted_at = models.DateTimeField(null=True, blank=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name="leads")
    general_notes = models.TextField(blank=True)
    partner = models.ForeignKey("partners.Partner", null=True, blank=True, on_delete=models.SET_NULL, related_name="leads")
    location_preference = models.CharField(max_length=200, blank=True)
    partner_submitted_notes = models.TextField(blank=True, max_length=10000)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        permissions = [("reassign_lead", "Can reassign accessible leads"), ("archive_lead", "Can archive accessible leads")]
        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=["NEW", "ASSIGNED", "CONTACTED", "INTERESTED", "COUNSELLING", "COURSE_SELECTED", "APPLICATION_STARTED", "APPLICATION_SUBMITTED", "PAYMENT_PENDING", "ADMISSION_CONFIRMED", "NOT_INTERESTED", "WRONG_NUMBER", "NO_RESPONSE", "NOT_ELIGIBLE", "LOST"]), name="leads_valid_status"),
            models.CheckConstraint(condition=models.Q(priority__in=["LOW", "MEDIUM", "HIGH", "URGENT"]), name="leads_valid_priority"),
            models.CheckConstraint(condition=models.Q(budget__gte=0) | models.Q(budget__isnull=True), name="leads_nonnegative_budget"),
        ]
        indexes = [models.Index(fields=["assigned_counsellor", "is_active", "-created_at"]), models.Index(fields=["assigned_team", "is_active", "status"])]

    def clean(self):
        from apps.universities.selection import validate_selection
        old = type(self).objects.filter(pk=self.pk).values_list("selected_country_id", "selected_university_id", "selected_course_id").first() if self.pk else None
        self.selected_country = validate_selection(self.selected_country, self.selected_university, self.selected_course,
            previous=old or (None, None, None))
        self.full_name = self.full_name.strip()
        if not self.full_name:
            raise ValidationError({"full_name": "Name is required."})
        for field in ("phone", "alternate_phone"):
            try:
                setattr(self, field, normalize_phone(getattr(self, field)))
            except ValidationError as exc:
                raise ValidationError({field: exc.messages})
        self.email = self.email.strip().lower()
        if self.date_of_birth and self.date_of_birth > timezone.localdate():
            raise ValidationError({"date_of_birth": "Date of birth cannot be in the future."})

    def __str__(self):
        return self.full_name


class LeadAssignment(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.PROTECT, related_name="assignment_history")
    previous_counsellor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="previous_lead_assignments")
    new_counsellor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="new_lead_assignments")
    previous_team = models.ForeignKey("accounts.Team", null=True, on_delete=models.PROTECT, related_name="previous_assignments")
    new_team = models.ForeignKey("accounts.Team", null=True, on_delete=models.PROTECT, related_name="new_assignments")
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    assigned_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ["assigned_at", "pk"]


class LeadStatusHistory(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.PROTECT, related_name="status_history")
    previous_status = models.CharField(max_length=32, choices=Lead.Status.choices, blank=True)
    new_status = models.CharField(max_length=32, choices=Lead.Status.choices)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    changed_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["changed_at", "pk"]


class LeadNote(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.PROTECT, related_name="notes")
    note = models.TextField(max_length=10000)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "pk"]
