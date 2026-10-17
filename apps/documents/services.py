from pathlib import Path
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from apps.applications.models import Application
from apps.applications.permissions import application_leads, visible_applications
from .models import Document, DocumentHistory
from .validators import validate_upload


def visible_documents(actor):
    return Document.objects.filter(application__in=visible_applications(actor))


def lock_application(actor, pk):
    app = get_object_or_404(visible_applications(actor), pk=pk)
    lead = get_object_or_404(application_leads(actor).select_for_update(), pk=app.lead_id)
    if not lead.is_active:
        raise ValidationError("Archived leads are read-only.")
    return get_object_or_404(Application.objects.select_for_update(), pk=pk, lead=lead)


def record(document, actor, action, previous="", **details):
    DocumentHistory.objects.create(document=document, actor=actor, action=action,
        previous_status=previous, new_status=document.status, details=details)


def create_document(actor, application_id, *, document_type, title, upload=None):
    saved_file = None
    try:
        with transaction.atomic():
            application = lock_application(actor, application_id)
            document = Document(application=application, lead=application.lead, document_type=document_type,
                title=title.strip(), created_by=actor, updated_by=actor)
            if upload:
                attach(document, upload)
            document.full_clean()
            if upload:
                document.file.save(upload.name, upload, save=False)
                saved_file = document.file.name
            document.save()
            record(document, actor, "UPLOADED" if upload else "REQUESTED", title=document.title,
                document_type=document.document_type, filename=document.original_name, size=document.size)
            return document
    except Exception:
        if saved_file:
            document.file.storage.delete(saved_file)
        raise


def attach(document, upload):
    document.content_type = validate_upload(upload)
    if document.document_type == Document.Type.PHOTO and not document.content_type.startswith("image/"):
        raise ValidationError("Photo documents must be PNG or JPEG images.")
    document.original_name = Path(upload.name.replace("\\", "/")).name[:255]
    document.size = upload.size
    document.status = Document.Status.SUBMITTED
    document.reviewed_by = None
    document.reviewed_at = None
    document.rejection_reason = ""
    document.verification_notes = ""


def update_document(actor, pk, *, action, upload=None, reason="", notes=""):
    saved_file = None
    try:
        with transaction.atomic():
            reference = get_object_or_404(visible_documents(actor), pk=pk, deleted_at__isnull=True)
            lock_application(actor, reference.application_id)
            document = get_object_or_404(Document.objects.select_for_update(), pk=pk, deleted_at__isnull=True)
            previous = document.status
            old_file = document.file.name
            details = {}
            if action == "upload":
                if not upload or previous not in ("PENDING", "REJECTED", "SUBMITTED"):
                    raise ValidationError("Upload a file to a pending, submitted or rejected document.")
                previous_filename = document.original_name
                attach(document, upload)
                details = {"previous_filename": previous_filename, "filename": document.original_name, "size": upload.size}
                document.file.save(upload.name, upload, save=False)
                saved_file = document.file.name
            elif action in ("verify", "reject"):
                if previous != "SUBMITTED" or not document.file:
                    raise ValidationError("Only submitted documents can be verified or rejected.")
                if action == "reject" and not reason.strip():
                    raise ValidationError("A rejection reason is required.")
                document.status = "VERIFIED" if action == "verify" else "REJECTED"
                document.rejection_reason = reason.strip() if action == "reject" else ""
                document.verification_notes = notes.strip()
                document.reviewed_by = actor
                document.reviewed_at = timezone.now()
                details = {"reason": document.rejection_reason, "notes": document.verification_notes}
            elif action == "delete":
                document.deleted_at = timezone.now()
                document.file = ""
                details = {"filename": document.original_name}
            else:
                raise ValidationError("Unsupported document action.")
            document.updated_by = actor
            document.full_clean()
            document.save()
            record(document, actor, action.upper(), previous, **details)
            if old_file and action in ("upload", "delete"):
                transaction.on_commit(lambda: document.file.storage.delete(old_file), robust=True)
            return document
    except Exception:
        if saved_file:
            document.file.storage.delete(saved_file)
        raise
