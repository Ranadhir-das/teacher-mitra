"""Partner onboarding uses the existing Partner and private Document records."""
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings
from apps.accounts.models import User
from apps.documents.models import Document
from apps.documents.services import attach, record
from .models import Partner, PartnerOnboardingHistory
from .permissions import onboarding_partner, can_manage_partners
from .services import check_fields, require_manager

FIELDS = ("business_name", "contact_person", "email", "phone", "alternate_phone", "partner_type", "address", "city", "state", "pincode", "tax_type", "tax_identifier", "tax_explanation")
EDITABLE_STATUSES = ("REGISTERED", "ONBOARDING", "CHANGES_REQUIRED")
DOCUMENT_TYPES = ("CANCELLED_CHEQUE", "TAX_DOCUMENT", "ID_ADDRESS_PROOF", "BUSINESS_PROOF", "OTHER")


def progress(partner):
    required = ["business_name", "contact_person", "email", "phone", "address", "city", "state", "pincode", "tax_type"]
    required.append("tax_explanation" if partner.tax_type == "NOT_APPLICABLE" else "tax_identifier")
    missing_fields = [field for field in required if not str(getattr(partner, field) or "").strip()]
    types = ["CANCELLED_CHEQUE", "ID_ADDRESS_PROOF"]
    if partner.tax_type in ("PAN", "GST"):
        types.append("TAX_DOCUMENT")
    if partner.partner_type not in ("INDIVIDUAL", "REFERRAL_AGENT"):
        types.append("BUSINESS_PROOF")
    types = list(dict.fromkeys(types + list(getattr(settings, "PARTNER_REQUIRED_DOCUMENT_TYPES", []))))
    documents = {doc.document_type: doc for doc in partner.onboarding_documents.filter(deleted_at__isnull=True)}
    missing_documents = [kind for kind in types if kind not in documents or not documents[kind].file or documents[kind].status not in ("SUBMITTED", "VERIFIED")]
    verified = all(kind in documents and documents[kind].status == "VERIFIED" for kind in types)
    total = len(required) + len(types)
    completed = total - len(missing_fields) - len(missing_documents)
    labels = dict(Document.Type.choices)
    return {"percent": round(completed * 100 / total), "complete": completed == total,
        "missing_fields": missing_fields, "missing_documents": missing_documents, "verified": verified,
        "requirements": [{"code": kind, "label": labels.get(kind, kind), "document": documents.get(kind)} for kind in types]}


def event(partner, actor, action, previous, note=""):
    PartnerOnboardingHistory.objects.create(partner=partner, actor=actor, action=action,
        previous_status=previous, new_status=partner.status, note=note)


def editable(partner):
    if partner.status not in EDITABLE_STATUSES:
        raise ValidationError("This onboarding is locked. An administrator must request changes before it can be edited.")


@transaction.atomic
def save_draft(actor, data):
    partner = onboarding_partner(actor, for_update=True)
    editable(partner)
    check_fields(data, FIELDS)
    previous = partner.status
    for field, value in data.items():
        setattr(partner, field, value)
    partner.tax_identifier = partner.tax_identifier.strip().upper()
    # Profile edits invalidate previous document reviews for the new submission.
    for doc in partner.onboarding_documents.filter(status="VERIFIED", deleted_at__isnull=True):
        doc.status = "SUBMITTED"
        doc.reviewed_at = doc.reviewed_by = None
        doc.save(update_fields=["status", "reviewed_at", "reviewed_by"])
        record(doc, actor, "REVIEW_RESET", "VERIFIED", reason="Onboarding information changed.")
    if partner.status == "REGISTERED":
        partner.status = "ONBOARDING"
    partner.full_clean()
    partner.save()
    event(partner, actor, "DRAFT_SAVED", previous)
    return partner


def upload_document(actor, kind, upload):
    stored = None
    try:
        with transaction.atomic():
            partner = onboarding_partner(actor, for_update=True)
            editable(partner)
            if kind not in DOCUMENT_TYPES:
                raise ValidationError("Unsupported onboarding document type.")
            document = partner.onboarding_documents.filter(document_type=kind, deleted_at__isnull=True).first()
            old_file = document.file.name if document else ""
            previous = document.status if document else ""
            if not document:
                document = Document(partner=partner, document_type=kind, title=dict(Document.Type.choices)[kind], created_by=actor)
            attach(document, upload)
            document.updated_by = actor
            document.full_clean()
            document.file.save(upload.name, upload, save=False)
            stored = document.file.name
            document.save()
            record(document, actor, "UPLOADED", previous, filename=document.original_name, size=document.size)
            if old_file:
                transaction.on_commit(lambda: document.file.storage.delete(old_file), robust=True)
            return document
    except Exception:
        if stored:
            document.file.storage.delete(stored)
        raise


@transaction.atomic
def submit_onboarding(actor):
    partner = onboarding_partner(actor, for_update=True)
    editable(partner)
    result = progress(partner)
    if not result["complete"]:
        raise ValidationError("Complete the required profile fields and upload all required documents before submitting.")
    previous = partner.status
    partner.status = "SUBMITTED"
    partner.submitted_at = timezone.now()
    partner.reviewed_at = None
    partner.reviewed_by = None
    partner.save()
    event(partner, actor, "SUBMITTED", previous)
    return partner


@transaction.atomic
def review_document(actor, pk, decision, reason=""):
    require_manager(actor)
    reference = get_object_or_404(Document, pk=pk, partner__isnull=False, deleted_at__isnull=True)
    partner = Partner.objects.select_for_update().get(pk=reference.partner_id)
    if partner.status != "SUBMITTED":
        raise ValidationError("Documents can be reviewed only after onboarding is submitted.")
    document = Document.objects.select_for_update().get(pk=pk)
    if decision not in ("verify", "reject") or not document.file:
        raise ValidationError("Choose verify or reject for an uploaded document.")
    if decision == "reject" and not reason.strip():
        raise ValidationError("Explain the document rejection.")
    previous = document.status
    document.status = "VERIFIED" if decision == "verify" else "REJECTED"
    document.rejection_reason = reason.strip() if decision == "reject" else ""
    document.reviewed_by = document.updated_by = actor
    document.reviewed_at = timezone.now()
    document.save()
    record(document, actor, decision.upper(), previous, reason=reason)
    return document


@transaction.atomic
def review_onboarding(actor, pk, decision, feedback=""):
    require_manager(actor)
    partner = get_object_or_404(Partner.objects.select_for_update(), pk=pk)
    if partner.status != "SUBMITTED":
        raise ValidationError("Only submitted onboarding can be reviewed.")
    if decision not in ("approve", "reject", "changes"):
        raise ValidationError("Choose approve, reject or request changes.")
    if decision != "approve" and not feedback.strip():
        raise ValidationError("Provide feedback for rejection or requested changes.")
    result = progress(partner)
    if decision == "approve" and (not result["complete"] or not result["verified"]):
        raise ValidationError("Complete onboarding and verify every required document before approval.")
    previous = partner.status
    partner.status = {"approve": "ACTIVE", "reject": "REJECTED", "changes": "CHANGES_REQUIRED"}[decision]
    partner.review_feedback = feedback.strip()
    partner.reviewed_by = actor
    partner.reviewed_at = timezone.now()
    partner.save()
    # Rejected applicants can still log in to see the decision, but never access leads.
    event(partner, actor, decision.upper(), previous, feedback.strip())
    return partner


def accessible_document(actor, pk):
    qs = Document.objects.filter(partner__isnull=False, deleted_at__isnull=True)
    if not can_manage_partners(actor):
        qs = qs.filter(partner=onboarding_partner(actor))
    return get_object_or_404(qs, pk=pk)
