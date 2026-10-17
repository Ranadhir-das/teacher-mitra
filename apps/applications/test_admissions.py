from datetime import timedelta
from unittest.mock import patch
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.http import Http404
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone
from apps.documents.test_support import WorkflowTestCase
from apps.leads.models import Lead
from .admissions import save_admission, visible_admissions
from .models import Admission, AdmissionHistory
from .services import save_application


class AdmissionTests(WorkflowTestCase):
    def save(self, **data):
        return save_admission(self.counsellor, self.application.pk, data)

    def confirm(self, **data):
        return self.save(status="CONFIRMED", enrollment_number="ENR-001", admission_date=timezone.localdate(), **data)

    def test_pending_links_and_history(self):
        admission = self.save(remarks="Awaiting offer")
        self.assertEqual(admission.application, self.application)
        self.assertEqual(admission.lead, self.lead)
        self.assertEqual(admission.course, self.course)
        self.assertEqual(admission.university, self.university)
        self.assertEqual(admission.status, "PENDING")
        self.assertEqual(admission.history.count(), 1)
        self.assertIsNone(admission.confirmed_at)

    def test_confirmation_synchronizes_application_and_lead(self):
        self.save()
        admission = self.confirm(payment_status="PAID")
        self.application.refresh_from_db()
        self.lead.refresh_from_db()
        self.assertEqual(admission.status, "CONFIRMED")
        self.assertEqual(admission.confirmed_by, self.counsellor)
        self.assertIsNotNone(admission.confirmed_at)
        self.assertEqual(self.application.status, "APPROVED")
        self.assertEqual(self.lead.status, "ADMISSION_CONFIRMED")
        self.assertEqual(self.application.history.last().new_status, "APPROVED")
        self.assertIn("Admission", self.lead.status_history.last().note)
        self.assertEqual(admission.history.count(), 2)

    def test_approval_alone_does_not_confirm_admission(self):
        save_application(self.counsellor, {"status": "APPROVED"}, pk=self.application.pk)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, "APPLICATION_SUBMITTED")
        self.assertFalse(Admission.objects.exists())
        self.confirm()
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, "ADMISSION_CONFIRMED")

    def test_confirmation_is_idempotent(self):
        admission = self.confirm()
        confirmation_time = admission.confirmed_at
        history_counts = (admission.history.count(), self.application.history.count(), self.lead.status_history.count())
        admission = self.confirm()
        self.assertEqual(admission.confirmed_at, confirmation_time)
        self.assertEqual((admission.history.count(), self.application.history.count(), self.lead.status_history.count()), history_counts)
        self.assertEqual(Admission.objects.count(), 1)

    def test_confirmation_requires_number_and_date(self):
        for data in ({"status": "CONFIRMED"}, {"status": "CONFIRMED", "enrollment_number": "ENR"},
                     {"status": "CONFIRMED", "enrollment_number": " ", "admission_date": timezone.localdate()}):
            with self.assertRaises(ValidationError):
                self.save(**data)
        self.assertFalse(Admission.objects.exists())

    def test_future_date_and_invalid_choices(self):
        for data in ({"admission_date": timezone.localdate() + timedelta(days=1)}, {"status": "BOGUS"},
                     {"payment_status": "BOGUS"}, {"status": "CANCELLED"}):
            with self.assertRaises(ValidationError):
                self.save(**data)

    def test_payment_status_and_remarks_audited(self):
        admission = self.save()
        for payment in Admission.PaymentStatus.values:
            admission = self.save(payment_status=payment, remarks=f"Payment: {payment}")
            self.assertEqual(admission.payment_status, payment)
        self.assertEqual(admission.history.last().changes["payment_status"]["after"], "REFUNDED")

    def test_cancel_terminal_but_details_remain_editable(self):
        self.confirm()
        admission = self.save(status="CANCELLED", remarks="Student withdrew", payment_status="REFUNDED")
        self.assertEqual(admission.status, "CANCELLED")
        with self.assertRaises(ValidationError):
            self.confirm()
        with self.assertRaises(ValidationError):
            self.save(status="PENDING")
        self.save(remarks="Refund complete")
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, "ADMISSION_CONFIRMED")

    def test_pending_admission_cancel_before_application_rejection(self):
        self.save()
        with self.assertRaises(ValidationError):
            save_application(self.counsellor, {"status": "REJECTED"}, pk=self.application.pk)
        self.save(status="CANCELLED")
        save_application(self.counsellor, {"status": "REJECTED"}, pk=self.application.pk)
        self.save(payment_status="REFUNDED", remarks="Refund after rejection")

    def test_unsubmitted_and_rejected_applications_cannot_enroll(self):
        draft = save_application(self.counsellor, {"university": self.university, "course": self.course}, lead_id=self.lead.pk)
        with self.assertRaises(ValidationError):
            save_admission(self.counsellor, draft.pk, {})
        save_application(self.counsellor, {"status": "REJECTED"}, pk=self.application.pk)
        with self.assertRaises(ValidationError):
            self.confirm()

    def test_scope_roles_reassignment_and_inactive(self):
        admission = self.save()
        for actor in (self.other, self.partner):
            self.assertFalse(visible_admissions(actor).exists())
            with self.assertRaises(Http404):
                save_admission(actor, self.application.pk, {"remarks": "No"})
        for actor in (self.admin, self.leader):
            save_admission(actor, self.application.pk, {"remarks": actor.name})
        self.counsellor.is_active = False
        with self.assertRaises(Http404):
            self.save()
        self.counsellor.is_active = True
        Lead.objects.filter(pk=self.lead.pk).update(assigned_counsellor=self.other)
        with self.assertRaises(Http404):
            self.save()
        save_admission(self.other, self.application.pk, {"remarks": "Reassigned"})
        admission.refresh_from_db()
        self.assertEqual(admission.updated_by, self.other)

    def test_archived_readonly(self):
        self.save()
        Lead.objects.filter(pk=self.lead.pk).update(is_active=False)
        with self.assertRaises(ValidationError):
            self.confirm()

    def test_mass_assignment_rejected(self):
        for field in ("lead", "course", "university", "application", "confirmed_by", "created_by"):
            with self.assertRaises(ValidationError):
                self.save(**{field: self.admin})

    def test_confirmation_rollback(self):
        self.save()
        with patch("apps.applications.admissions.LeadStatusHistory.objects.create", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.confirm()
        self.application.refresh_from_db()
        self.lead.refresh_from_db()
        admission = Admission.objects.get()
        self.assertEqual(admission.status, "PENDING")
        self.assertEqual(self.application.status, "SUBMITTED")
        self.assertEqual(self.lead.status, "APPLICATION_SUBMITTED")
        self.assertEqual(admission.history.count(), 1)

    def test_sibling_application_does_not_regress_confirmation(self):
        self.confirm()
        sibling = save_application(self.counsellor, {"university": self.university, "course": self.course, "status": "STARTED"}, lead_id=self.lead.pk)
        save_application(self.counsellor, {"status": "CANCELLED"}, pk=sibling.pk)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, "ADMISSION_CONFIRMED")

    def test_unique_constraints_and_protection(self):
        admission = self.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Admission.objects.filter(pk=admission.pk).update(status="BOGUS")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Admission.objects.filter(pk=admission.pk).update(payment_status="BOGUS")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Admission.objects.create(application=self.application, lead=self.lead, course=self.course,
                university=self.university, created_by=self.admin, updated_by=self.admin)
        with self.assertRaises(ProtectedError):
            admission.delete()

    def test_web_confirmation_detail_and_csrf(self):
        self.client.force_login(self.counsellor)
        url = reverse("applications:admission-edit", args=[self.application.pk])
        response = self.client.post(url, {"status": "CONFIRMED", "payment_status": "PAID", "enrollment_number": "ENR-WEB", "admission_date": str(timezone.localdate()), "remarks": "Welcome"})
        self.assertRedirects(response, reverse("applications:detail", args=[self.application.pk]))
        response = self.client.get(reverse("applications:detail", args=[self.application.pk]))
        for text in ("ENR-WEB", "Paid", "Confirmed", "Welcome", "Admission history"):
            self.assertContains(response, text)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.counsellor)
        self.assertEqual(csrf.post(url, {"status": "CANCELLED"}).status_code, 403)

    def test_web_invalid_confirmation_and_unauthorized(self):
        self.client.force_login(self.counsellor)
        url = reverse("applications:admission-edit", args=[self.application.pk])
        response = self.client.post(url, {"status": "CONFIRMED", "payment_status": "PENDING"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(Admission.objects.exists())
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {"status": "CONFIRMED"}).status_code, 404)
        response = self.client.post(reverse("applications:admission-create"), {"application": self.application.pk, "status": "PENDING", "payment_status": "PENDING"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Admission.objects.exists())

    def test_admin_management_scope_and_audit_readonly(self):
        admission = self.save()
        self.client.force_login(self.counsellor)
        self.assertRedirects(self.client.get(reverse("admin:applications_admission_add")), reverse("applications:admission-create"))
        self.assertContains(self.client.get(reverse("admin:applications_admission_change", args=[admission.pk])), "Manage admission / enrollment")
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse("admin:applications_admission_changelist")), "Confidential student")
        request = RequestFactory().get("/admin/")
        request.user = self.other
        self.assertFalse(admin.site._registry[Admission].has_view_permission(request, admission))
        self.assertFalse(admin.site._registry[AdmissionHistory].has_view_permission(request, admission.history.first()))
        self.assertFalse(admin.site._registry[Admission].has_delete_permission(request, admission))
