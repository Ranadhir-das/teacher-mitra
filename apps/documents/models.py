import uuid
from pathlib import Path
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from .storage import PrivateDocumentStorage


def document_path(instance, filename):
    return f"documents/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class Document(models.Model):
    class Type(models.TextChoices):
        CANCELLED_CHEQUE = "CANCELLED_CHEQUE", "Cancelled cheque"
        TAX_DOCUMENT = "TAX_DOCUMENT", "PAN / GST document"
        ID_ADDRESS_PROOF = "ID_ADDRESS_PROOF", "ID / address proof"
        BUSINESS_PROOF = "BUSINESS_PROOF", "Business / organisation proof"
        PHOTO = "PHOTO", "Photo"
        ID_PROOF = "ID_PROOF", "ID proof"
        ACADEMIC_CERTIFICATE = "ACADEMIC_CERTIFICATE", "Academic certificate"
        MARKSHEET = "MARKSHEET", "Marksheet"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUBMITTED = "SUBMITTED", "Submitted"
        VERIFIED = "VERIFIED", "Verified"
        REJECTED = "REJECTED", "Rejected"

    application = models.ForeignKey("applications.Application", null=True, blank=True, on_delete=models.PROTECT, related_name="documents")
    lead = models.ForeignKey("leads.Lead", null=True, blank=True, on_delete=models.PROTECT, related_name="documents")
    partner = models.ForeignKey("partners.Partner", null=True, blank=True, on_delete=models.PROTECT, related_name="onboarding_documents")
    document_type = models.CharField(max_length=24, choices=Type.choices)
    title = models.CharField(max_length=200)
    file = models.FileField(storage=PrivateDocumentStorage(), upload_to=document_path, blank=True, max_length=255)
    original_name = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=50, blank=True)
    size = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField(blank=True, max_length=5000)
    verification_notes = models.TextField(blank=True, max_length=5000)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="reviewed_documents")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_documents")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="updated_documents")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [models.CheckConstraint(condition=models.Q(status__in=["PENDING", "SUBMITTED", "VERIFIED", "REJECTED"]), name="document_valid_status"),
            models.CheckConstraint(condition=(models.Q(partner__isnull=False, application__isnull=True, lead__isnull=True) | models.Q(partner__isnull=True, application__isnull=False, lead__isnull=False)), name="document_single_owner"),
            models.UniqueConstraint(fields=["partner", "document_type"], condition=models.Q(partner__isnull=False, deleted_at__isnull=True), name="partner_current_document_type"),
        ]

    def clean(self):
        if self.partner_id:
            if self.application_id or self.lead_id:
                raise ValidationError("A partner document cannot belong to an application or lead.")
        elif not self.application_id or not self.lead_id:
            raise ValidationError("An application document requires both application and lead.")
        if self.application_id and self.lead_id != self.application.lead_id:
            raise ValidationError("Document lead must match its application.")

    def __str__(self):
        return self.title


class DocumentHistory(models.Model):
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="history")
    action = models.CharField(max_length=20)
    previous_status = models.CharField(max_length=12, blank=True, choices=Document.Status.choices)
    new_status = models.CharField(max_length=12, choices=Document.Status.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(default=dict)

    class Meta:
        ordering = ["created_at", "pk"]
