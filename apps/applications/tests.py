from datetime import timedelta
from unittest.mock import patch
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.http import Http404
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import User
from apps.courses.models import Course
from apps.leads.models import Lead
from apps.universities.models import Country, University
from .forms import ApplicationForm
from .models import Application, ApplicationStatusHistory
from .permissions import application_leads, visible_applications
from .services import save_application


@override_settings(SECURE_SSL_REDIRECT=False)
class ApplicationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("app-admin@example.com", name="Admin", role="ADMIN", is_staff=True)
        cls.leader = User.objects.create_user("app-leader@example.com", name="Leader", role="TEAM_LEADER", is_staff=True)
        cls.counsellor = User.objects.create_user("app-counsellor@example.com", name="Counsellor", is_staff=True)
        cls.other = User.objects.create_user("app-other@example.com", name="Other", is_staff=True)
        cls.partner = User.objects.create_user("app-partner@example.com", name="Partner", role="PARTNER")
        cls.university = University.objects.create(country=Country.objects.get_or_create(name="Test Country")[0], name="Application University")
        cls.second_university = University.objects.create(country=Country.objects.get_or_create(name="Test Country")[0], name="Second University")
        cls.course = Course.objects.create(university=cls.university, name="MBA", program="MBA", duration_months=24,
            fees=1000, eligibility="Graduate", mode="ONLINE", intake="2027")
        cls.lead = Lead.objects.create(full_name="Private Student", phone="9876543210", created_by=cls.admin,
            updated_by=cls.admin, assigned_counsellor=cls.counsellor)
        cls.other_lead = Lead.objects.create(full_name="Other Student", phone="9876543211", created_by=cls.admin,
            updated_by=cls.admin, assigned_counsellor=cls.other)

    def create(self, **overrides):
        return save_application(self.counsellor, {"university": self.university, "course": self.course, **overrides}, lead_id=self.lead.pk)

    def post_data(self, **overrides):
        return {"lead": self.lead.pk, "university": self.university.pk, "course": self.course.pk,
                "status": "DRAFT", "reference": "REF-001", "academic_details": "BSc, 2024, 85%", "remarks": "Initial", **overrides}

    def progress(self, application, statuses=("STARTED", "SUBMITTED", "UNDER_REVIEW", "APPROVED")):
        for status in statuses:
            application = save_application(self.counsellor, {"status": status}, pk=application.pk)
        return application

    def test_creation_and_snapshot(self):
        application = self.create(reference="REF", academic_details="BSc", remarks="Discussed")
        self.assertEqual(application.status, "DRAFT")
        self.assertEqual(application.created_by, self.counsellor)
        self.assertEqual(application.lead, self.lead)
        event = application.history.get()
        self.assertEqual(event.previous_status, "")
        self.assertEqual(event.changes["academic_details"]["after"], "BSc")
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, "NEW")

    def test_progression_and_lead_history(self):
        application = self.create()
        expected = (("STARTED", "APPLICATION_STARTED"), ("SUBMITTED", "APPLICATION_SUBMITTED"),
                    ("UNDER_REVIEW", "APPLICATION_SUBMITTED"), ("APPROVED", "APPLICATION_SUBMITTED"))
        for status, lead_status in expected:
            application = save_application(self.counsellor, {"status": status}, pk=application.pk)
            self.lead.refresh_from_db()
            self.assertEqual(self.lead.status, lead_status)
        self.assertEqual(application.submission_date, timezone.localdate())
        self.assertEqual(application.history.count(), 5)
        self.assertEqual(self.lead.status_history.count(), 2)
        self.assertEqual(self.lead.status_history.last().changed_by, self.counsellor)

    def test_details_edits_audited_and_noop_not_duplicated(self):
        application = self.create()
        save_application(self.counsellor, {"remarks": "New remarks"}, pk=application.pk)
        save_application(self.counsellor, {"remarks": "New remarks"}, pk=application.pk)
        event = application.history.last()
        self.assertEqual(application.history.count(), 2)
        self.assertEqual(event.previous_status, event.new_status)
        self.assertEqual(event.changes, {"remarks": {"before": "", "after": "New remarks"}})

    def test_allowed_terminal_decisions(self):
        for status in ("REJECTED", "CANCELLED", "APPROVED"):
            with self.subTest(status=status):
                application = self.progress(self.create(), ("STARTED", "SUBMITTED", status))
                self.assertEqual(application.status, status)
                with self.assertRaises(ValidationError):
                    save_application(self.admin, {"status": "STARTED"}, pk=application.pk)

    def test_invalid_transition_is_atomic(self):
        application = self.create()
        for status in ("SUBMITTED", "APPROVED", "BOGUS"):
            with self.assertRaises(ValidationError):
                save_application(self.counsellor, {"status": status, "remarks": "Must roll back"}, pk=application.pk)
        application.refresh_from_db()
        self.assertEqual(application.remarks, "")
        self.assertEqual(application.history.count(), 1)

    def test_creation_cannot_skip_workflow(self):
        for status in ("SUBMITTED", "UNDER_REVIEW", "APPROVED", "REJECTED", "CANCELLED", "BOGUS"):
            with self.assertRaises(ValidationError):
                self.create(status=status)
        self.assertEqual(Application.objects.count(), 0)

    def test_multiple_applications_never_regress_lead(self):
        approved = self.progress(self.create())
        second = self.progress(self.create(), ("STARTED", "SUBMITTED", "REJECTED"))
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, "APPLICATION_SUBMITTED")
        self.assertEqual(approved.status, "APPROVED")
        self.assertEqual(second.status, "REJECTED")

    def test_payment_pending_not_regressed(self):
        Lead.objects.filter(pk=self.lead.pk).update(status="PAYMENT_PENDING")
        self.progress(self.create(), ("STARTED", "SUBMITTED"))
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, "PAYMENT_PENDING")

    def test_submission_date_validation_and_retention(self):
        with self.assertRaises(ValidationError):
            self.create(submission_date=timezone.localdate())
        application = self.create(status="STARTED")
        with self.assertRaises(ValidationError):
            save_application(self.counsellor, {"status": "SUBMITTED", "submission_date": timezone.localdate() + timedelta(days=1)}, pk=application.pk)
        submitted = timezone.localdate() - timedelta(days=2)
        application = save_application(self.counsellor, {"status": "SUBMITTED", "submission_date": submitted}, pk=application.pk)
        application = save_application(self.counsellor, {"status": "CANCELLED", "submission_date": None}, pk=application.pk)
        self.assertEqual(application.submission_date, submitted)

    def test_catalogue_validation_and_closed_existing_offering(self):
        with self.assertRaises(ValidationError):
            self.create(university=self.second_university)
        application = self.create()
        Course.objects.filter(pk=self.course.pk).update(is_active=False, intake_status="CLOSED")
        University.objects.filter(pk=self.university.pk).update(is_active=False)
        self.course.refresh_from_db()
        self.university.refresh_from_db()
        with self.assertRaises(ValidationError):
            self.create()
        self.progress(application)
        form = ApplicationForm(instance=application, actor=self.counsellor)
        self.assertIn(self.course, form.fields["course"].queryset)
        self.assertIn(self.university, form.fields["university"].queryset)

    def test_offering_and_lead_immutable_after_submission(self):
        application = self.progress(self.create(), ("STARTED", "SUBMITTED"))
        alternative = Course.objects.create(university=self.second_university, name="MA", program="MA", duration_months=12,
            fees=100, eligibility="Graduate", mode="ONLINE", intake="2027")
        with self.assertRaises(ValidationError):
            save_application(self.counsellor, {"university": self.second_university, "course": alternative}, pk=application.pk)
        application.lead = self.other_lead
        with self.assertRaises(ValidationError):
            application.full_clean()
        self.course.university = self.second_university
        with self.assertRaises(ValidationError):
            self.course.full_clean()

    def test_archive_readonly(self):
        application = self.create()
        Lead.objects.filter(pk=self.lead.pk).update(is_active=False)
        with self.assertRaises(ValidationError):
            self.create()
        with self.assertRaises(ValidationError):
            save_application(self.admin, {"remarks": "No"}, pk=application.pk)
        self.client.force_login(self.counsellor)
        self.assertContains(self.client.get(reverse("applications:detail", args=[application.pk])), "Archived lead: read-only")

    def test_service_permissions_and_reassignment(self):
        application = self.create()
        for actor in (self.other, self.partner):
            self.assertFalse(visible_applications(actor).exists())
            with self.assertRaises(Http404):
                save_application(actor, {"remarks": "No"}, pk=application.pk)
            with self.assertRaises(Http404):
                save_application(actor, {"university": self.university, "course": self.course}, lead_id=self.lead.pk)
        for actor in (self.admin, self.leader):
            self.assertEqual(visible_applications(actor).count(), 1)
            save_application(actor, {"remarks": actor.name}, pk=application.pk)
        Lead.objects.filter(pk=self.lead.pk).update(assigned_counsellor=self.other)
        self.assertFalse(visible_applications(self.counsellor).exists())
        save_application(self.other, {"remarks": "Now assigned"}, pk=application.pk)

    def test_inactive_user_denied(self):
        application = self.create()
        self.counsellor.is_active = False
        self.assertFalse(application_leads(self.counsellor).exists())
        with self.assertRaises(Http404):
            save_application(self.counsellor, {}, pk=application.pk)

    def test_untrusted_fields_rejected(self):
        for field, value in (("lead", self.other_lead), ("created_by", self.admin), ("updated_by", self.admin), ("id", 100)):
            with self.assertRaises(ValidationError):
                self.create(**{field: value})

    def test_transaction_rolls_back_on_audit_failure(self):
        with patch("apps.applications.services.ApplicationStatusHistory.objects.create", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.create(status="STARTED")
        self.assertEqual(Application.objects.count(), 0)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, "NEW")

    def test_database_constraint_and_protected_records(self):
        application = self.create()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Application.objects.filter(pk=application.pk).update(status="BOGUS")
        for obj in (application, self.lead, self.course, self.university):
            with self.assertRaises(ProtectedError):
                obj.delete()

    def test_web_create_update_detail_and_timeline(self):
        self.client.force_login(self.counsellor)
        response = self.client.post(reverse("applications:create"), self.post_data())
        application = Application.objects.get()
        self.assertRedirects(response, reverse("applications:detail", args=[application.pk]))
        self.client.post(reverse("applications:edit", args=[application.pk]), self.post_data(status="STARTED", remarks="Revised"))
        response = self.client.get(reverse("applications:detail", args=[application.pk]))
        for text in ("Complete timeline", "REF-001", "BSc, 2024, 85%", "Revised", "Initial", "Counsellor"):
            self.assertContains(response, text)
        self.assertEqual(application.history.count(), 2)

    def test_web_access_and_forged_lead(self):
        application = self.create()
        self.client.force_login(self.other)
        for action in ("detail", "edit"):
            url = reverse("applications:" + action, args=[application.pk])
            self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(reverse("applications:edit", args=[application.pk]), self.post_data()).status_code, 404)
        response = self.client.post(reverse("applications:create"), self.post_data())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Application.objects.count(), 1)
        self.assertNotContains(self.client.get(reverse("applications:list")), "Private Student")
        self.assertEqual(self.client.get(reverse("applications:create"), {"lead": self.lead.pk}).status_code, 404)
        self.client.force_login(self.counsellor)
        self.client.post(reverse("applications:edit", args=[application.pk]), self.post_data(lead=self.other_lead.pk))
        application.refresh_from_db()
        self.assertEqual(application.lead_id, self.lead.pk)

    def test_partner_anonymous_and_csrf(self):
        self.assertEqual(self.client.get(reverse("applications:list")).status_code, 302)
        self.client.force_login(self.partner)
        self.assertEqual(self.client.get(reverse("applications:list")).status_code, 403)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.counsellor)
        self.assertEqual(client.post(reverse("applications:create"), self.post_data()).status_code, 403)

    def test_filter_pagination_and_prefill(self):
        self.client.force_login(self.counsellor)
        self.create(reference="FINDME")
        for index in range(25):
            self.create(reference=f"OTHER-{index}")
        response = self.client.get(reverse("applications:list"), {"search": "FINDME", "status": "DRAFT"})
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        response = self.client.get(reverse("applications:list"), {"page": 2})
        self.assertEqual(len(response.context["page_obj"]), 1)
        response = self.client.get(reverse("applications:list"), {"lead": "invalid"})
        self.assertEqual(response.context["page_obj"].paginator.count, 0)
        Lead.objects.filter(pk=self.lead.pk).update(selected_course=self.course, selected_university=self.university, highest_qualification="BSc")
        response = self.client.get(reverse("applications:create"), {"lead": self.lead.pk})
        self.assertEqual(response.context["form"].initial["course"], self.course.pk)
        self.assertEqual(response.context["form"].initial["academic_details"], "BSc")

    def test_invalid_web_form_no_writes(self):
        self.client.force_login(self.counsellor)
        for changes in ({"university": self.second_university.pk}, {"status": "APPROVED"}, {"status": "BOGUS"}, {"course": ""}, {"submission_date": "2099-01-01"}):
            response = self.client.post(reverse("applications:create"), self.post_data(**changes))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["form"].errors)
        self.assertEqual(Application.objects.count(), 0)

    def test_admin_create_update_history_and_isolation(self):
        self.client.force_login(self.counsellor)
        response = self.client.get(reverse("admin:applications_application_add"))
        self.assertEqual(response.status_code, 200)
        data = {**self.post_data(), "history-TOTAL_FORMS": 0, "history-INITIAL_FORMS": 0, "history-MIN_NUM_FORMS": 0, "history-MAX_NUM_FORMS": 0}
        response = self.client.post(reverse("admin:applications_application_add"), data)
        self.assertEqual(response.status_code, 302)
        application = Application.objects.get()
        response = self.client.post(reverse("admin:applications_application_change", args=[application.pk]), {**data, "status": "STARTED", "history-TOTAL_FORMS": 1, "history-INITIAL_FORMS": 1, "history-0-id": application.history.get().pk})
        self.assertEqual(response.status_code, 302)
        application.refresh_from_db()
        self.assertEqual(application.status, "STARTED")
        self.assertEqual(application.history.count(), 2)
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse("admin:applications_application_changelist")), "Private Student")
        request = RequestFactory().get("/admin/")
        request.user = self.other
        registered = admin.site._registry[Application]
        self.assertFalse(registered.has_change_permission(request, application))
        self.assertFalse(registered.has_delete_permission(request, application))
        audit = admin.site._registry[ApplicationStatusHistory]
        self.assertFalse(audit.has_view_permission(request, application.history.first()))
        self.assertFalse(audit.has_add_permission(request))
        self.assertFalse(audit.has_change_permission(request))

    def test_team_leader_all_applications_without_expanding_lead_access(self):
        application = self.create()
        self.client.force_login(self.leader)
        response = self.client.get(reverse("applications:detail", args=[application.pk]))
        self.assertContains(response, "Private Student")
        self.assertFalse(response.context["can_view_lead"])
        self.assertEqual(self.client.post(reverse("applications:edit", args=[application.pk]), self.post_data(status="STARTED")).status_code, 302)
        self.assertEqual(self.client.post(reverse("applications:create"), self.post_data(lead=self.other_lead.pk)).status_code, 302)
