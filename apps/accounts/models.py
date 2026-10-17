import uuid
from pathlib import Path
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower
from django.core.validators import RegexValidator
from .managers import UserManager


def profile_photo_path(instance, filename):
    return f"profiles/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class User(AbstractUser):
    class Role(models.TextChoices):
        SUPER_ADMIN = "SUPER_ADMIN", "Super admin"
        ADMIN = "ADMIN", "Admin"
        TEAM_LEADER = "TEAM_LEADER", "Team leader"
        COUNSELLOR = "COUNSELLOR", "Counsellor"
        PARTNER = "PARTNER", "Partner"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"
        BLOCKED = "BLOCKED", "Blocked"

    username = models.CharField(max_length=150, null=True, blank=True, unique=True,
        validators=[RegexValidator(r"^[a-zA-Z0-9_.-]+$", "Use letters, numbers, dots, underscores or hyphens.")])
    employee_id = models.CharField(max_length=50, null=True, blank=True, unique=True)
    joining_date = models.DateField(null=True, blank=True)
    account_status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    profile_information = models.TextField(blank=True, max_length=10000)
    first_name = None
    last_name = None
    name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=30, blank=True)
    profile_photo = models.ImageField(upload_to=profile_photo_path, blank=True)
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.COUNSELLOR)
    objects = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        ordering = ["name", "pk"]
        constraints = [models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
            models.UniqueConstraint(Lower("username"), name="accounts_username_ci_unique"),
            models.UniqueConstraint(Lower("employee_id"), name="accounts_employee_id_ci_unique"),
            models.CheckConstraint(condition=models.Q(account_status__in=["ACTIVE", "INACTIVE", "BLOCKED"]), name="accounts_valid_status"),
            models.CheckConstraint(condition=~models.Q(role="PARTNER") | models.Q(is_staff=False, is_superuser=False), name="accounts_partner_not_staff")]

    def clean(self):
        super().clean()
        self.email = self.email.lower()
        self.username = self.username.strip().lower() if self.username else None
        self.employee_id = self.employee_id.strip().upper() if self.employee_id else None
        from django.core.exceptions import ValidationError
        if self.role == self.Role.PARTNER and (self.is_staff or self.is_superuser):
            raise ValidationError("Partner accounts cannot have staff or superuser access.")
        if self.pk and hasattr(self, "partner_profile") and self.role != self.Role.PARTNER:
            raise ValidationError("A linked partner account must retain the Partner role.")

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        self.username = self.username.strip().lower() if self.username else None
        self.employee_id = self.employee_id.strip().upper() if self.employee_id else None
        previous = type(self).objects.filter(pk=self.pk).values("account_status", "is_active").first() if self.pk else None
        fields = kwargs.get("update_fields")
        if fields is not None and "is_active" in fields and "account_status" not in fields:
            self.account_status = self.Status.ACTIVE if self.is_active else self.Status.INACTIVE
        elif previous and previous["account_status"] == self.account_status and previous["is_active"] != self.is_active:
            self.account_status = self.Status.ACTIVE if self.is_active else self.Status.INACTIVE
        elif not previous and self.account_status == self.Status.ACTIVE and not self.is_active:
            self.account_status = self.Status.INACTIVE
        self.is_active = self.account_status == self.Status.ACTIVE
        if fields is not None and ({"account_status", "is_active"} & set(fields)):
            kwargs["update_fields"] = set(fields) | {"account_status", "is_active"}
        super().save(*args, **kwargs)

    def get_full_name(self):
        return self.name

    def get_short_name(self):
        return self.name.split()[0] if self.name else self.email

    def __str__(self):
        return f"{self.name} <{self.email}>"


class Team(models.Model):
    name = models.CharField(max_length=120, unique=True)
    leader = models.ForeignKey(User, on_delete=models.PROTECT, related_name="led_teams",
                               limit_choices_to={"role": User.Role.TEAM_LEADER, "is_active": True})
    members = models.ManyToManyField(User, related_name="crm_teams", blank=True,
                                    limit_choices_to={"role": User.Role.COUNSELLOR, "is_active": True})
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Counsellor(User):
    """Admin facade for the existing User table, not a second account model."""
    class Meta:
        proxy = True
        verbose_name = "Counsellor"
        verbose_name_plural = "Counsellors"


class CounsellorHistory(models.Model):
    counsellor = models.ForeignKey(User, on_delete=models.PROTECT, related_name="counsellor_history")
    actor = models.ForeignKey(User, on_delete=models.PROTECT, related_name="counsellor_management_history")
    action = models.CharField(max_length=30)
    changes = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
