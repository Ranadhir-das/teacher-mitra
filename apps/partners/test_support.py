"""Complete the real onboarding flow in tests that require an approved partner."""
import tempfile
from django.test import override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from . import onboarding


def prepared_submission(partner, admin):
    with tempfile.TemporaryDirectory() as directory, override_settings(PRIVATE_DOCUMENT_ROOT=directory):
        onboarding.save_draft(partner.user, {"address": "Example address", "city": "Pune", "state": "MH", "pincode": "411001", "tax_type": "NOT_APPLICABLE", "tax_explanation": "Outside applicable tax registration; review requested."})
        partner.refresh_from_db()
        for item in onboarding.progress(partner)["requirements"]:
            onboarding.upload_document(partner.user, item["code"], SimpleUploadedFile("proof.pdf", b"%PDF-1.4\nTest document\n%%EOF", content_type="application/pdf"))
        onboarding.submit_onboarding(partner.user)
        for doc in partner.onboarding_documents.all():
            onboarding.review_document(admin, doc.pk, "verify")
        partner.refresh_from_db()
