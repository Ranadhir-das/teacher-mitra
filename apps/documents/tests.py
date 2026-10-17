from pathlib import Path
from unittest.mock import patch
from django.conf import settings
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.http import Http404
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse
from apps.leads.models import Lead
from .models import Document, DocumentHistory
from .services import create_document, update_document, visible_documents
from .test_support import WorkflowTestCase, image_upload


class DocumentTests(WorkflowTestCase):
    def create(self, upload=None, **kwargs):
        return create_document(self.counsellor, self.application.pk, document_type="PHOTO", title="Identity photo", upload=upload, **kwargs)

    def test_pending_request_and_upload(self):
        document = self.create()
        self.assertEqual(document.status, "PENDING")
        self.assertFalse(document.file)
        document = update_document(self.counsellor, document.pk, action="upload", upload=image_upload())
        self.assertEqual(document.status, "SUBMITTED")
        self.assertEqual(document.lead, self.lead)
        self.assertEqual(document.content_type, "image/png")
        self.assertEqual(document.history.count(), 2)
        self.assertTrue(document.file.storage.exists(document.file.name))

    def test_upload_private_storage_and_random_filename(self):
        document = self.create(image_upload("secret.png"))
        self.assertNotIn("secret", document.file.name)
        self.assertEqual(document.original_name, "secret.png")
        self.assertTrue(Path(document.file.path).is_relative_to(Path(settings.PRIVATE_DOCUMENT_ROOT)))
        with self.assertRaises(ValueError):
            _ = document.file.url

    def test_verify_and_reject_details(self):
        document = self.create(image_upload())
        document = update_document(self.admin, document.pk, action="reject", reason="Blurry image", notes="Use a clearer scan")
        self.assertEqual(document.status, "REJECTED")
        self.assertEqual(document.rejection_reason, "Blurry image")
        self.assertEqual(document.reviewed_by, self.admin)
        self.assertIsNotNone(document.reviewed_at)
        document = update_document(self.counsellor, document.pk, action="upload", upload=image_upload())
        self.assertEqual(document.rejection_reason, "")
        self.assertIsNone(document.reviewed_by)
        self.assertIsNone(document.reviewed_at)
        document = update_document(self.counsellor, document.pk, action="verify", notes="Matches applicant")
        self.assertEqual(document.status, "VERIFIED")
        self.assertEqual(document.verification_notes, "Matches applicant")
        self.assertEqual(document.history.count(), 4)
        self.assertEqual(document.history.get(action="REJECT").details["reason"], "Blurry image")

    def test_invalid_review_transitions(self):
        document = self.create()
        for action in ("verify", "reject", "unknown", "upload"):
            with self.assertRaises(ValidationError):
                update_document(self.counsellor, document.pk, action=action)
        document = update_document(self.counsellor, document.pk, action="upload", upload=image_upload())
        with self.assertRaises(ValidationError):
            update_document(self.counsellor, document.pk, action="reject", reason="  ")
        update_document(self.counsellor, document.pk, action="verify")
        with self.assertRaises(ValidationError):
            update_document(self.counsellor, document.pk, action="upload", upload=image_upload())

    def test_invalid_uploads_and_types(self):
        invalid = [("bad.exe", b"MZ..."), ("bad.png", b"not png"), ("bad.pdf", b"%PDF-1.7 corrupt"),
                   ("empty.png", b""), ("bad.svg", b"<svg></svg>")]
        for name, content in invalid:
            with self.subTest(name=name), self.assertRaises(ValidationError):
                self.create(SimpleUploadedFile(name, content))
        with self.assertRaises(ValidationError):
            create_document(self.counsellor, self.application.pk, document_type="BOGUS", title="Invalid")
        with self.assertRaises(ValidationError):
            create_document(self.counsellor, self.application.pk, document_type="OTHER", title="   ")
        self.assertFalse(Document.objects.exists())

    @override_settings(DOCUMENT_MAX_UPLOAD_SIZE=10)
    def test_upload_size_limit(self):
        with self.assertRaises(ValidationError):
            self.create(image_upload())

    def test_pdf_allowed_except_photo(self):
        content = b"%PDF-1.4\n1 0 obj<</Type /Catalog>>endobj\n%%EOF"
        document = create_document(self.counsellor, self.application.pk, document_type="ACADEMIC_CERTIFICATE",
            title="Degree", upload=SimpleUploadedFile("degree.pdf", content))
        self.assertEqual(document.content_type, "application/pdf")
        with self.assertRaises(ValidationError):
            self.create(SimpleUploadedFile("photo.pdf", content))

    def test_extension_mismatch(self):
        with self.assertRaises(ValidationError):
            self.create(image_upload("fake.jpg"))

    def test_upload_replaces_file_after_commit(self):
        document = self.create(image_upload("old.png"))
        old = document.file.name
        with self.captureOnCommitCallbacks(execute=True):
            document = update_document(self.counsellor, document.pk, action="upload", upload=image_upload("new.png"))
        self.assertFalse(document.file.storage.exists(old))
        self.assertTrue(document.file.storage.exists(document.file.name))
        self.assertEqual(document.history.last().details["previous_filename"], "old.png")

    def test_delete_removes_file_and_preserves_history(self):
        document = self.create(image_upload())
        old = document.file.name
        with self.captureOnCommitCallbacks(execute=True):
            document = update_document(self.counsellor, document.pk, action="delete")
        self.assertIsNotNone(document.deleted_at)
        self.assertFalse(document.file)
        self.assertFalse(document.file.storage.exists(old))
        self.assertEqual(document.history.last().action, "DELETE")
        with self.assertRaises(Http404):
            update_document(self.counsellor, document.pk, action="upload", upload=image_upload())
        self.client.force_login(self.counsellor)
        self.assertEqual(self.client.get(reverse("documents:download", args=[document.pk])).status_code, 404)
        self.assertContains(self.client.get(reverse("documents:detail", args=[document.pk])), "Deleted")

    def test_rollback_cleans_new_file(self):
        with patch("apps.documents.services.record", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.create(image_upload())
        self.assertFalse(Document.objects.exists())
        self.assertFalse(list(Path(settings.PRIVATE_DOCUMENT_ROOT).rglob("*.png")))

    def test_replacement_rollback_preserves_original(self):
        document = self.create(image_upload("original.png"))
        original = document.file.name
        with patch("apps.documents.services.record", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                update_document(self.counsellor, document.pk, action="upload", upload=image_upload("replacement.png"))
        document.refresh_from_db()
        self.assertEqual(document.file.name, original)
        self.assertEqual(len(list(Path(settings.PRIVATE_DOCUMENT_ROOT).rglob("*.png"))), 1)

    def test_scope_roles_and_reassignment(self):
        document = self.create(image_upload())
        for actor in (self.other, self.partner):
            self.assertFalse(visible_documents(actor).exists())
            with self.assertRaises(Http404):
                update_document(actor, document.pk, action="verify")
            with self.assertRaises(Http404):
                create_document(actor, self.application.pk, document_type="OTHER", title="No")
        self.assertTrue(visible_documents(self.leader).exists())
        Lead.objects.filter(pk=self.lead.pk).update(assigned_counsellor=self.other)
        self.assertFalse(visible_documents(self.counsellor).exists())
        update_document(self.other, document.pk, action="verify")

    def test_inactive_and_archived(self):
        document = self.create(image_upload())
        self.counsellor.is_active = False
        with self.assertRaises(Http404):
            update_document(self.counsellor, document.pk, action="verify")
        Lead.objects.filter(pk=self.lead.pk).update(is_active=False)
        with self.assertRaises(ValidationError):
            update_document(self.admin, document.pk, action="delete")
        with self.assertRaises(ValidationError):
            create_document(self.admin, self.application.pk, document_type="OTHER", title="No")

    def test_authorized_view_download_headers_and_missing_files(self):
        document = self.create(image_upload())
        self.client.force_login(self.counsellor)
        for action, disposition in (("view", "inline"), ("download", "attachment")):
            response = self.client.get(reverse("documents:" + action, args=[document.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response["Content-Disposition"].startswith(disposition))
            self.assertEqual(response["Cache-Control"], "private, no-store")
            self.assertEqual(response["X-Content-Type-Options"], "nosniff")
            self.assertTrue(b"".join(response.streaming_content).startswith(b"\x89PNG"))
            response.close()
        document.file.storage.delete(document.file.name)
        self.assertEqual(self.client.get(reverse("documents:download", args=[document.pk])).status_code, 404)

    def test_other_user_cannot_access_any_document_route(self):
        document = self.create(image_upload())
        self.client.force_login(self.other)
        for action in ("view", "download", "detail"):
            self.assertEqual(self.client.get(reverse("documents:" + action, args=[document.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("documents:detail", args=[document.pk]), {"action": "delete"}).status_code, 404)
        self.assertEqual(self.client.get(reverse("documents:application-create", args=[self.application.pk])).status_code, 404)

    def test_web_create_review_application_detail_and_csrf(self):
        self.client.force_login(self.counsellor)
        response = self.client.post(reverse("documents:application-create", args=[self.application.pk]),
            {"document_type": "PHOTO", "title": "Passport photo", "upload": image_upload()})
        document = Document.objects.get()
        self.assertRedirects(response, reverse("documents:detail", args=[document.pk]))
        response = self.client.post(reverse("documents:detail", args=[document.pk]), {"action": "reject", "reason": "Blurry"})
        self.assertEqual(response.status_code, 302)
        response = self.client.get(reverse("applications:detail", args=[self.application.pk]))
        self.assertContains(response, "Passport photo")
        self.assertContains(response, "Blurry")
        self.assertContains(response, "Document activity")
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.counsellor)
        self.assertEqual(csrf.post(reverse("documents:detail", args=[document.pk]), {"action": "delete"}).status_code, 403)

    def test_invalid_web_upload_and_forged_application(self):
        self.client.force_login(self.counsellor)
        response = self.client.post(reverse("documents:create"), {"application": self.application.pk, "document_type": "PHOTO", "title": "Bad", "upload": SimpleUploadedFile("bad.png", b"bad")})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.client.force_login(self.other)
        response = self.client.post(reverse("documents:create"), {"application": self.application.pk, "document_type": "PHOTO", "title": "No"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Document.objects.exists())

    def test_anonymous_partner_and_public_media_access(self):
        document = self.create(image_upload())
        self.assertEqual(self.client.get(reverse("documents:download", args=[document.pk])).status_code, 302)
        self.assertEqual(self.client.get("/media/" + document.file.name).status_code, 404)
        self.client.force_login(self.partner)
        self.assertEqual(self.client.get(reverse("documents:download", args=[document.pk])).status_code, 403)

    def test_admin_management_and_audit_scope(self):
        document = self.create(image_upload())
        self.client.force_login(self.counsellor)
        self.assertRedirects(self.client.get(reverse("admin:documents_document_add")), reverse("documents:create"))
        self.assertContains(self.client.get(reverse("admin:documents_document_change", args=[document.pk])), "View, download, upload, review or delete")
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse("admin:documents_document_changelist")), "Identity photo")
        request = RequestFactory().get("/admin/")
        request.user = self.other
        self.assertFalse(admin.site._registry[Document].has_view_permission(request, document))
        self.assertFalse(admin.site._registry[DocumentHistory].has_view_permission(request, document.history.first()))
        self.assertFalse(admin.site._registry[Document].has_delete_permission(request, document))

    def test_constraints_and_protected_history(self):
        document = self.create()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Document.objects.filter(pk=document.pk).update(status="INVALID")
        with self.assertRaises(ProtectedError):
            document.delete()
