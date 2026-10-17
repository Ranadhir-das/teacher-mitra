from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class FollowUp(models.Model):

    class Type(models.TextChoices):
        CALL = "CALL", "Phone call"
        WHATSAPP = "WHATSAPP", "WhatsApp"
        EMAIL = "EMAIL", "Email"
        MEETING = "MEETING", "Meeting"
        REMINDER = "REMINDER", "Reminder"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Scheduled"
        COMPLETED = "COMPLETED", "Completed"
        MISSED = "MISSED", "Missed"
        CANCELLED = "CANCELLED", "Cancelled"

    lead = models.ForeignKey(
        "leads.Lead",
        on_delete=models.PROTECT,
        related_name="followups",
    )

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assigned_followups",
    )

    followup_type = models.CharField(
        max_length=20,
        choices=Type.choices,
        default=Type.CALL,
        db_index=True,
    )

    scheduled_at = models.DateTimeField(
        db_index=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SCHEDULED,
        db_index=True,
    )

    outcome = models.CharField(
        max_length=500,
        blank=True,
    )

    notes = models.TextField(
        blank=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_followups",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["scheduled_at", "pk"]
        indexes = [
            models.Index(
                fields=["assigned_to", "status", "scheduled_at"]
            ),
            models.Index(
                fields=["lead", "status", "scheduled_at"]
            ),
        ]

    def clean(self):
        if self.status == self.Status.COMPLETED and not self.completed_at:
            self.completed_at = timezone.now()

        if self.status != self.Status.COMPLETED:
            self.completed_at = None

    def __str__(self):
        return (
            f"{self.get_followup_type_display()} - "
            f"{self.lead.full_name} - "
            f"{self.scheduled_at:%Y-%m-%d %H:%M}"
        )