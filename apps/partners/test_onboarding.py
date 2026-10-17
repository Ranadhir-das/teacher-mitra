import tempfile
from django.test import TestCase, override_settings, Client
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from rest_framework.test import APIClient
from apps.accounts.models import User
from apps.documents.models import Document
from . import services, onboarding
from .models import Partner

PASSWORD = "Cedar-River-Partner-97!"


@override_settings(SECURE_SSL_REDIRECT=False)
class OnboardingTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings_override = override_settings(PRIVATE_DOCUMENT_ROOT=self.directory.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.admin = User.objects.create_user("onboarding-admin@example.com", name="Admin", role="ADMIN")
        self.staff = User.objects.create_user("onboarding-staff@example.com", name="Staff")
        self.partner = services.register_partner({"business_name": "Example partner", "contact_person": "Asha", "email": "newpartner@example.com", "phone": "9876543210", "partner_type": "INDIVIDUAL"}, PASSWORD)
        self.user = self.partner.user
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def file(self, data=b"%PDF-1.4\nPrivate document\n%%EOF", name="proof.pdf"):
        return SimpleUploadedFile(name, data, content_type="application/pdf")

    def complete(self, business=False):
        onboarding.save_draft(self.user, {"address": "Address", "city": "Pune", "state": "MH", "pincode": "411001", "tax_type": "PAN", "tax_identifier": "ABCDE1234F", "partner_type": "CORPORATE" if business else "INDIVIDUAL"})
        self.partner.refresh_from_db()
        for requirement in onboarding.progress(self.partner)["requirements"]:
            onboarding.upload_document(self.user, requirement["code"], self.file())
        onboarding.submit_onboarding(self.user)
        self.partner.refresh_from_db()

    def verify(self):
        for doc in self.partner.onboarding_documents.all():
            onboarding.review_document(self.admin, doc.pk, "verify")

    def test_signup_login_limited_dashboard_and_api_gates(self):
        self.assertTrue(self.client.login(email=self.user.email, password=PASSWORD))
        self.assertContains(self.client.get(reverse("partner-portal:dashboard")), "Complete your onboarding")
        for route in ("leads", "submit", "reports", "profile"):
            self.assertEqual(self.client.get(reverse("partner-portal:" + route)).status_code, 403)
        self.assertEqual(self.api.get(reverse("partner-api:leads")).status_code, 403)
        self.assertEqual(self.api.post(reverse("partner-api:leads"), {"full_name": "Blocked", "phone": "9876543219"}).status_code, 403)
        self.assertEqual(self.api.get(reverse("partner-api:onboarding")).status_code, 200)
        with self.assertRaises(PermissionDenied):
            services.submit_lead(self.user, {"full_name": "Blocked", "phone": "9876543219"})

    def test_draft_progress_upload_validation_and_submit(self):
        response = self.api.patch(reverse("partner-api:onboarding"), {"address": "Saved address"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "ONBOARDING")
        self.assertEqual(self.api.patch(reverse("partner-api:onboarding"), {"status": "ACTIVE"}).status_code, 400)
        with self.assertRaises(ValidationError):
            onboarding.submit_onboarding(self.user)
        for file in (self.file(b"not PDF"), self.file(name="proof.exe")):
            with self.assertRaises(ValidationError):
                onboarding.upload_document(self.user, "CANCELLED_CHEQUE", file)
        self.assertFalse(Document.objects.exists())
        self.complete(business=True)
        self.assertEqual(self.partner.status, "SUBMITTED")
        self.assertEqual(onboarding.progress(self.partner)["percent"], 100)
        self.assertEqual(self.partner.onboarding_documents.count(), 4)
        with self.assertRaises(ValidationError):
            onboarding.save_draft(self.user, {"business_name": "Changed during review"})
        with self.assertRaises(ValidationError):
            onboarding.upload_document(self.user, "CANCELLED_CHEQUE", self.file())

    def test_document_verification_required_then_full_access(self):
        self.complete()
        with self.assertRaises(ValidationError):
            onboarding.review_onboarding(self.admin, self.partner.pk, "approve")
        self.verify()
        partner = onboarding.review_onboarding(self.admin, self.partner.pk, "approve")
        self.assertEqual(partner.status, "ACTIVE")
        self.assertEqual(self.api.get(reverse("partner-api:leads")).status_code, 200)
        response = self.api.post(reverse("partner-api:leads"), {"full_name": "Approved student", "phone": "9876543219"})
        self.assertEqual(response.status_code, 201)
        self.assertTrue(partner.onboarding_history.filter(action="APPROVE").exists())

    def test_changes_replacement_and_resubmission(self):
        self.complete()
        doc = self.partner.onboarding_documents.first()
        onboarding.review_document(self.admin, doc.pk, "reject", "Unreadable image")
        with self.assertRaises(ValidationError):
            onboarding.review_onboarding(self.admin, self.partner.pk, "changes")
        onboarding.review_onboarding(self.admin, self.partner.pk, "changes", "Replace the unreadable proof")
        self.assertEqual(self.api.get(reverse("partner-api:onboarding")).data["feedback"], "Replace the unreadable proof")
        with self.assertRaises(ValidationError):
            onboarding.submit_onboarding(self.user)
        replaced = onboarding.upload_document(self.user, doc.document_type, self.file())
        self.assertEqual(replaced.pk, doc.pk)
        self.assertEqual(replaced.status, "SUBMITTED")
        onboarding.submit_onboarding(self.user)
        self.verify()
        onboarding.review_onboarding(self.admin, self.partner.pk, "approve")
        self.assertEqual(self.api.get(reverse("partner-api:leads")).status_code, 200)

    def test_rejection_keeps_limited_login_and_blocks_mutation(self):
        self.complete()
        onboarding.review_onboarding(self.admin, self.partner.pk, "reject", "Unable to verify identity")
        self.assertTrue(self.client.login(email=self.user.email, password=PASSWORD))
        self.assertContains(self.client.get(reverse("partner-portal:dashboard")), "Unable to verify identity")
        self.assertEqual(self.api.get(reverse("partner-api:leads")).status_code, 403)
        with self.assertRaises(ValidationError):
            onboarding.save_draft(self.user, {"city": "Other"})

    def test_private_documents_owner_admin_only(self):
        doc = onboarding.upload_document(self.user, "CANCELLED_CHEQUE", self.file())
        self.assertIsNone(doc.application_id)
        self.assertIsNone(doc.lead_id)
        with self.assertRaises(ValueError):
            _ = doc.file.url
        url = reverse("partner-api:onboarding-file", args=[doc.pk])
        response = self.api.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertIn("attachment", response["Content-Disposition"])
        response.close()
        other = services.register_partner({"business_name": "Other", "contact_person": "Other", "email": "otheronboard@example.com", "phone": "9876543218"}, PASSWORD)
        self.api.force_authenticate(other.user)
        self.assertEqual(self.api.get(url).status_code, 404)
        self.api.force_authenticate(self.staff)
        self.assertEqual(self.api.get(reverse("partner-document-review-api", args=[doc.pk])).status_code, 403)
        self.api.force_authenticate(self.admin)
        response = self.api.get(reverse("partner-document-review-api", args=[doc.pk]))
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_admin_api_no_status_shortcuts_and_csrf(self):
        self.api.force_authenticate(self.admin)
        url = reverse("partner-onboarding-review-api", args=[self.partner.pk])
        self.assertEqual(self.api.post(url, {"decision": "approve"}).status_code, 400)
        self.assertEqual(self.api.patch(f"/api/v1/partners/{self.partner.pk}/", {"status": "ACTIVE"}).status_code, 400)
        self.complete()
        self.assertEqual(self.api.get(url).status_code, 200)
        for doc in self.partner.onboarding_documents.all():
            self.assertEqual(self.api.post(reverse("partner-document-review-api", args=[doc.pk]), {"decision": "verify"}).status_code, 200)
        self.assertEqual(self.api.post(url, {"decision": "approve"}).status_code, 200)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse("partner-portal:onboarding-submit")).status_code, 403)
        client.force_login(self.admin)
        self.assertEqual(client.post(reverse("partners:onboarding", args=[self.partner.pk]), {"decision": "approve"}).status_code, 403)

    def test_tax_nonapplicability_requires_explanation(self):
        onboarding.save_draft(self.user, {"tax_type": "NOT_APPLICABLE"})
        self.partner.refresh_from_db()
        self.assertIn("tax_explanation", onboarding.progress(self.partner)["missing_fields"])
        self.assertNotIn("TAX_DOCUMENT", [item["code"] for item in onboarding.progress(self.partner)["requirements"]])

    def test_web_onboarding_and_admin_review_screens(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("partner-portal:onboarding")), "Save and continue later")
        self.complete()
        self.assertContains(self.client.get(reverse("partner-portal:onboarding")), "Submitted for review")
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("partners:onboarding", args=[self.partner.pk])), "Verify document")
        doc = self.partner.onboarding_documents.first()
        response = self.client.post(reverse("partners:document-review", args=[doc.pk]), {"decision": "verify"})
        self.assertEqual(response.status_code, 302)
        response = self.client.post(reverse("partners:onboarding", args=[self.partner.pk]), {"decision": "changes", "feedback": "Update the address"})
        self.assertEqual(response.status_code, 302)
        self.partner.refresh_from_db()
        self.assertEqual(self.partner.status, "CHANGES_REQUIRED")

    def test_public_api_signup_and_real_login(self):
        api = APIClient()
        data = {"business_name": "API signup", "contact_person": "Sam", "email": "api-signup@example.com", "phone": "9876543211", "partner_type": "INDIVIDUAL", "city": "", "state": "", "password": PASSWORD, "password_confirm": PASSWORD}
        self.assertEqual(api.post("/api/v1/partners/signup/", {**data, "status": "ACTIVE"}).status_code, 400)
        self.assertEqual(api.post("/api/v1/partners/signup/", data).status_code, 201)
        self.assertEqual(api.post("/api/v1/partners/signup/", data).status_code, 400)
        response = api.post(reverse("auth-api:login"), {"email": data["email"], "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        api.credentials(HTTP_AUTHORIZATION="Bearer " + response.data["access"])
        self.assertEqual(api.get(reverse("partner-api:onboarding")).status_code, 200)
        self.assertEqual(api.get(reverse("partner-api:leads")).status_code, 403)

    def test_suspension_restore_requires_prior_approval(self):
        self.complete()
        self.verify()
        onboarding.review_onboarding(self.admin, self.partner.pk, "approve")
        services.update_partner(self.admin, self.partner.pk, {"status": "SUSPENDED"})
        self.user.refresh_from_db()
        with self.assertRaises(PermissionDenied):
            services.submit_lead(self.user, {"full_name": "Blocked", "phone": "9876543219"})
        services.update_partner(self.admin, self.partner.pk, {"status": "ACTIVE"})
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertEqual(self.api.get(reverse("partner-api:leads")).status_code, 200)
