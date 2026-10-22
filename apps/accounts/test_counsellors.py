from datetime import timedelta
from unittest.mock import patch
from django.contrib import admin
from django.contrib.auth import authenticate
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from apps.leads.models import Lead, LeadStatusHistory
from apps.applications.models import Application
from apps.applications.services import save_application
from apps.applications.admissions import save_admission
from apps.followups.models import FollowUp
from apps.universities.models import Country, University
from apps.courses.models import Course
from .models import User, Team, Counsellor, CounsellorHistory
from .counsellor_services import save_counsellor, reset_counsellor_password
from .counsellor_permissions import visible_counsellors, can_edit_counsellor
from .counsellor_queries import counsellor_workload

PASSWORD = "Cedar-Counsellor-947!"
NEW_PASSWORD = "Fresh-Oak-Password-639!"


@override_settings(SECURE_SSL_REDIRECT=False, PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CounsellorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser("root-counsellors@example.com", PASSWORD, name="Root")
        cls.admin = User.objects.create_user("admin-counsellors@example.com", PASSWORD, name="Admin", role="ADMIN", is_staff=True)
        cls.leader = User.objects.create_user("leader-counsellors@example.com", PASSWORD, name="Leader", role="TEAM_LEADER", is_staff=True)
        cls.other_leader = User.objects.create_user("leader-other@example.com", PASSWORD, name="Other leader", role="TEAM_LEADER")
        cls.team = Team.objects.create(name="North", leader=cls.leader)
        cls.other_team = Team.objects.create(name="South", leader=cls.other_leader)
        cls.worker = save_counsellor(cls.admin, {"name": "North Counsellor", "email": "north@example.com", "username": "north.user", "employee_id": "EMP-001", "phone": "9876543210"}, teams=[cls.team], password=PASSWORD)
        cls.other = save_counsellor(cls.admin, {"name": "South Counsellor", "email": "south@example.com", "username": "south.user", "employee_id": "EMP-002"}, teams=[cls.other_team], password=PASSWORD)
        cls.partner = User.objects.create_user("counsellor-partner@example.com", PASSWORD, name="Partner", role="PARTNER")
        cls.university = University.objects.create(country=Country.objects.get_or_create(name="Test Country")[0], name="Counsellor University")
        cls.course = Course.objects.create(university=cls.university, name="MBA", program="MBA", duration_months=24,
            fees=1000, eligibility="Graduate", mode="ONLINE", intake="2027")
        cls.lead = Lead.objects.create(full_name="North Student", phone="9876543211", created_by=cls.admin, updated_by=cls.admin, assigned_counsellor=cls.worker, assigned_team=cls.team)
        cls.other_lead = Lead.objects.create(full_name="South Private Student", phone="9876543212", created_by=cls.admin, updated_by=cls.admin, assigned_counsellor=cls.other, assigned_team=cls.other_team)
        cls.application = save_application(cls.worker, {"university": cls.university, "course": cls.course, "status": "STARTED"}, lead_id=cls.lead.pk)
        cls.other_application = save_application(cls.other, {"university": cls.university, "course": cls.course, "status": "STARTED"}, lead_id=cls.other_lead.pk)
        cls.followup = FollowUp.objects.create(lead=cls.lead, assigned_to=cls.worker, created_by=cls.admin, scheduled_at=timezone.now() + timedelta(minutes=1))
        cls.other_followup = FollowUp.objects.create(lead=cls.other_lead, assigned_to=cls.other, created_by=cls.admin, scheduled_at=timezone.now())

    def setUp(self):
        cache.clear()

    def data(self, **overrides):
        return {"name": "New Counsellor", "email": "new-counsellor@example.com", "username": "new.counsellor",
                "employee_id": "EMP-003", "phone": "9876543214", "joining_date": timezone.localdate(),
                "account_status": "ACTIVE", "profile_information": "MBA admissions specialist", **overrides}

    def post_data(self, **overrides):
        return {**self.data(), "teams": [self.team.pk], "password1": PASSWORD, "password2": PASSWORD, **overrides}

    def test_create_reuses_user_and_team(self):
        target = save_counsellor(self.admin, self.data(), teams=[self.team], password=PASSWORD)
        self.assertEqual(target.role, "COUNSELLOR")
        self.assertTrue(target.is_active)
        self.assertFalse(target.is_staff or target.is_superuser)
        self.assertTrue(target.check_password(PASSWORD))
        self.assertEqual(list(target.crm_teams.all()), [self.team])
        self.assertEqual(target.profile_information, "MBA admissions specialist")
        self.assertEqual(User.objects.filter(pk=target.pk).count(), 1)
        self.assertEqual(Counsellor.objects.get(pk=target.pk).pk, target.pk)
        self.assertNotIn(PASSWORD, str(target.counsellor_history.get().changes))

    def test_normalization_and_case_insensitive_logins(self):
        target = save_counsellor(self.admin, self.data(email="MIXED@EXAMPLE.COM", username="Mixed.User", employee_id="emp-mixed", phone="+91 98765 43210"), password=PASSWORD)
        self.assertEqual(target.username, "mixed.user")
        self.assertEqual(target.employee_id, "EMP-MIXED")
        self.assertEqual(target.phone, "919876543210")
        self.assertEqual(authenticate(username="MIXED.USER", password=PASSWORD), target)
        self.assertEqual(authenticate(email="MIXED@EXAMPLE.COM", password=PASSWORD), target)

    def test_web_username_login(self):
        response = self.client.post(reverse("accounts:login"), {"username": "NORTH.USER", "password": PASSWORD})
        self.assertRedirects(response, reverse("dashboard:index"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.worker.pk)

    def test_api_username_login_and_missing_identifier(self):
        api = APIClient()
        response = api.post("/api/v1/auth/login/", {"username": "NORTH.USER", "password": PASSWORD}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertEqual(api.post("/api/v1/auth/login/", {"password": PASSWORD}, format="json").status_code, 400)
        self.assertEqual(api.post("/api/v1/auth/login/", {"email": self.worker.email, "username": self.worker.username, "password": PASSWORD}, format="json").status_code, 400)

    def test_duplicate_identity_fields(self):
        for changes in ({"email": self.worker.email.upper()}, {"username": self.worker.username.upper()}, {"employee_id": self.worker.employee_id.lower()}):
            with self.assertRaises(ValidationError):
                save_counsellor(self.admin, self.data(**changes), password=PASSWORD)
        self.assertFalse(User.objects.filter(email="new-counsellor@example.com").exists())

    def test_database_identity_and_status_constraints(self):
        for changes in ({"username": self.worker.username.upper()}, {"employee_id": self.worker.employee_id.lower()}, {"account_status": "INVALID"}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                User.objects.filter(pk=self.other.pk).update(**changes)

    def test_invalid_inputs_and_passwords(self):
        for changes in ({"username": "a@example.com"}, {"employee_id": " "}, {"name": " "}, {"email": "bad"}, {"phone": "abc"}, {"account_status": "INVALID"}):
            with self.assertRaises(ValidationError):
                save_counsellor(self.admin, self.data(**changes), password=PASSWORD)
        for password in (None, "123", "password"):
            with self.assertRaises(ValidationError):
                save_counsellor(self.admin, self.data(), password=password)

    def test_create_from_ui_keeps_manager_logged_in(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("accounts:employee-create"), self.post_data(role="COUNSELLOR", is_staff="on", is_superuser="on"))
        target = User.objects.get(username="new.counsellor")
        self.assertRedirects(response, reverse("accounts:employee-detail", args=[target.pk]))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.admin.pk)
        self.assertEqual(target.role, "COUNSELLOR")
        self.assertFalse(target.is_staff or target.is_superuser)

    def test_team_leader_creation_and_cross_team_rejection(self):
        target = save_counsellor(self.leader, self.data(), teams=[self.team], password=PASSWORD)
        self.assertTrue(can_edit_counsellor(self.leader, target))
        for teams in ([], [self.other_team], [self.team, self.other_team]):
            with self.assertRaises(ValidationError):
                save_counsellor(self.leader, self.data(email="second@example.com", username="second", employee_id="SECOND"), teams=teams, password=PASSWORD)
        with self.assertRaises(ValidationError):
            save_counsellor(self.leader, self.data(email="second@example.com", username="second", employee_id="SECOND"), password=PASSWORD)

    def test_leader_ui_create_and_forged_team(self):
        self.client.force_login(self.leader)
        response = self.client.post(reverse("accounts:employee-create"), self.post_data(teams=[self.other_team.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="new.counsellor").exists())
        response = self.client.post(reverse("accounts:employee-create"), self.post_data())
        self.assertEqual(response.status_code, 302)

    def test_leader_edit_status_and_team_scope(self):
        target = save_counsellor(self.leader, {"name": "Updated", "account_status": "INACTIVE"}, pk=self.worker.pk)
        self.assertFalse(target.is_active)
        with self.assertRaises(Http404):
            save_counsellor(self.leader, {"name": "No"}, pk=self.other.pk)
        with self.assertRaises(ValidationError):
            save_counsellor(self.leader, {}, pk=self.worker.pk, teams=[self.other_team])

    def test_shared_and_privileged_counsellors_require_admin(self):
        self.worker.crm_teams.add(self.other_team)
        self.assertIn(self.worker, visible_counsellors(self.leader))
        self.assertFalse(can_edit_counsellor(self.leader, self.worker))
        with self.assertRaises(PermissionDenied):
            save_counsellor(self.leader, {"name": "No"}, pk=self.worker.pk)
        self.worker.crm_teams.remove(self.other_team)
        self.worker.is_staff = True
        self.worker.save()
        for actor in (self.leader, self.admin):
            with self.assertRaises(PermissionDenied):
                save_counsellor(actor, {"name": "No"}, pk=self.worker.pk)
        save_counsellor(self.root, {"name": "Allowed"}, pk=self.worker.pk)

    def test_counsellor_partner_and_inactive_manager_denied(self):
        for actor in (self.worker, self.partner):
            with self.assertRaises(PermissionDenied):
                save_counsellor(actor, self.data(), password=PASSWORD)
            self.assertFalse(visible_counsellors(actor).exists())
        self.admin.is_active = False
        with self.assertRaises(PermissionDenied):
            save_counsellor(self.admin, self.data(), password=PASSWORD)

    def test_role_and_privilege_mass_assignment_denied(self):
        for field in ("role", "is_staff", "is_superuser", "groups", "is_active", "password"):
            with self.assertRaises(ValidationError):
                save_counsellor(self.admin, {field: "ADMIN"}, pk=self.worker.pk)

    def test_status_blocks_login_sessions_and_tokens(self):
        api = APIClient()
        for status in ("INACTIVE", "BLOCKED"):
            save_counsellor(self.admin, {"account_status": "ACTIVE"}, pk=self.worker.pk)
            self.worker.refresh_from_db()
            self.client.force_login(self.worker)
            tokens = api.post("/api/v1/auth/login/", {"email": self.worker.email, "password": PASSWORD}, format="json").data
            target = save_counsellor(self.admin, {"account_status": status}, pk=self.worker.pk)
            self.assertFalse(target.is_active)
            self.assertIsNone(authenticate(username=target.username, password=PASSWORD))
            self.assertEqual(self.client.get(reverse("dashboard:index")).status_code, 302)
            api.credentials(HTTP_AUTHORIZATION="Bearer " + tokens["access"])
            self.assertEqual(api.get("/api/v1/auth/me/").status_code, 401)
            self.assertEqual(api.post("/api/v1/auth/refresh/", {"refresh": tokens["refresh"]}).status_code, 401)
            api.credentials()

    def test_reactivation_and_legacy_is_active_writes(self):
        self.worker.is_active = False
        self.worker.save(update_fields=["is_active"])
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.account_status, "INACTIVE")
        target = save_counsellor(self.admin, {"account_status": "ACTIVE"}, pk=self.worker.pk)
        self.assertTrue(target.is_active)
        self.assertEqual(authenticate(username=target.username, password=PASSWORD), target)
        target.account_status = "BLOCKED"
        target.save(update_fields=["account_status"])
        target.refresh_from_db()
        self.assertFalse(target.is_active)

    def test_password_reset_revokes_sessions_access_and_refresh(self):
        self.client.force_login(self.worker)
        api = APIClient()
        tokens = api.post("/api/v1/auth/login/", {"username": self.worker.username, "password": PASSWORD}, format="json").data
        target = reset_counsellor_password(self.admin, self.worker.pk, NEW_PASSWORD)
        self.assertTrue(target.check_password(NEW_PASSWORD))
        self.assertFalse(target.check_password(PASSWORD))
        self.assertEqual(self.client.get(reverse("dashboard:index")).status_code, 302)
        api.credentials(HTTP_AUTHORIZATION="Bearer " + tokens["access"])
        self.assertEqual(api.get("/api/v1/auth/me/").status_code, 401)
        self.assertEqual(api.post("/api/v1/auth/refresh/", {"refresh": tokens["refresh"]}).status_code, 401)
        event = target.counsellor_history.first()
        self.assertEqual(event.action, "PASSWORD_RESET")
        self.assertEqual(event.changes, {})

    def test_password_reset_authorization_and_validation(self):
        for actor in (self.leader, self.worker, self.partner):
            with self.assertRaises((PermissionDenied, Http404)):
                reset_counsellor_password(actor, self.worker.pk, NEW_PASSWORD)
        with self.assertRaises(ValidationError):
            reset_counsellor_password(self.admin, self.worker.pk, "123")
        with self.assertRaises(ValidationError):
            save_counsellor(self.admin, {}, pk=self.worker.pk, password=NEW_PASSWORD)

    def test_noop_and_audited_changes(self):
        count = self.worker.counsellor_history.count()
        save_counsellor(self.admin, {}, pk=self.worker.pk)
        self.assertEqual(self.worker.counsellor_history.count(), count)
        target = save_counsellor(self.admin, {"profile_information": "Updated skills"}, pk=self.worker.pk, teams=[self.other_team])
        event = target.counsellor_history.first()
        self.assertEqual(event.changes["teams"]["after"], [self.other_team.pk])
        self.assertEqual(event.changes["profile_information"]["after"], "Updated skills")
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.assigned_team, self.team)
        self.assertEqual(self.lead.assigned_counsellor, self.worker)

    def test_atomic_rollback(self):
        with patch("apps.accounts.counsellor_services.CounsellorHistory.objects.create", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                save_counsellor(self.admin, self.data(), teams=[self.team], password=PASSWORD)
        self.assertFalse(User.objects.filter(username="new.counsellor").exists())

    def test_inactive_teams_cannot_be_new_assignments(self):
        self.other_team.is_active = False
        self.other_team.save()
        with self.assertRaises(ValidationError):
            save_counsellor(self.admin, self.data(), teams=[self.other_team], password=PASSWORD)
        save_counsellor(self.admin, {"name": "Existing inactive membership"}, pk=self.other.pk, teams=[self.other_team])

    def test_list_search_filter_pagination_and_access(self):
        self.client.force_login(self.admin)
        for query in ({"q": "EMP-001"}, {"q": "north.user"}, {"team": self.team.pk}, {"q": "north@example.com"}):
            response = self.client.get(reverse("accounts:employee-list"), query)
            self.assertEqual(response.context["page_obj"].paginator.count, 1)
        save_counsellor(self.admin, {"account_status": "BLOCKED"}, pk=self.other.pk)
        response = self.client.get(reverse("accounts:employee-list"), {"status": "BLOCKED"})
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        for i in range(21):
            User.objects.create_user(f"pagination-{i}@example.com", name=f"Pagination {i}")
        response = self.client.get(reverse("accounts:employee-list"), {"q": "Pagination", "page": 2})
        self.assertEqual(len(response.context["page_obj"]), 1)
        self.assertIn("q=Pagination", response.context["query"])
        self.client.force_login(self.leader)
        self.assertNotContains(self.client.get(reverse("accounts:employee-list")), "South Counsellor")
        self.assertEqual(self.client.get(reverse("accounts:employee-detail", args=[self.other.pk])).status_code, 404)

    def test_profile_workload_and_conversion_statistics(self):
        save_application(self.worker, {"status": "SUBMITTED"}, pk=self.application.pk)
        save_admission(self.worker, self.application.pk, {"status": "CONFIRMED", "enrollment_number": "COUNS-ENR", "admission_date": timezone.localdate()})
        self.client.force_login(self.admin)
        response = self.client.get(reverse("accounts:employee-detail", args=[self.worker.pk]))
        self.assertContains(response, "North Student")
        self.assertNotContains(response, "South Private Student")
        self.assertEqual(response.context["performance"]["assigned_leads"], 1)
        self.assertEqual(response.context["performance"]["confirmed_admissions"], 1)
        self.assertEqual(response.context["performance"]["conversion_rate"], 100.0)
        self.assertEqual(response.context["application_page"].paginator.count, 1)
        self.assertEqual(response.context["followup_page"].paginator.count, 1)

    def test_profile_does_not_expand_leader_lead_scope(self):
        Lead.objects.filter(pk=self.other_lead.pk).update(assigned_counsellor=self.worker)
        self.client.force_login(self.leader)
        response = self.client.get(reverse("accounts:employee-detail", args=[self.worker.pk]))
        self.assertNotContains(response, "South Private Student")
        self.assertEqual(response.context["performance"]["assigned_leads"], 1)

    def test_counsellor_dashboard_workload_and_recent_activity_isolation(self):
        self.client.force_login(self.worker)
        response = self.client.get(reverse("dashboard:index"))
        self.assertContains(response, "Today's follow-ups")
        self.assertContains(response, "Pending applications")
        self.assertContains(response, "Recent activity")
        self.assertContains(response, "North Student")
        self.assertNotContains(response, "South Private Student")
        self.assertEqual(list(response.context["pending_applications"]), [self.application])
        self.assertEqual(list(response.context["today_followups"]), [self.followup])
        self.assertEqual(response.context["performance"]["assigned_leads"], 1)
        self.assertEqual(self.client.get(reverse("accounts:employee-list")).status_code, 403)

    def test_dashboard_excludes_other_assignees_and_completed_followups(self):
        FollowUp.objects.filter(pk=self.followup.pk).update(status="COMPLETED", completed_at=timezone.now())
        FollowUp.objects.create(lead=self.lead, assigned_to=self.other, created_by=self.admin, scheduled_at=timezone.now())
        workload = counsellor_workload(self.worker, self.worker)
        self.assertEqual(workload["today_followups"].count(), 0)
        self.assertEqual(workload["performance"]["completed_followups"], 1)
        Lead.objects.filter(pk=self.lead.pk).update(assigned_counsellor=self.other)
        workload = counsellor_workload(self.worker, self.worker)
        self.assertEqual(workload["performance"]["assigned_leads"], 0)
        self.assertEqual(workload["recent_activity"], [])

    def test_ui_edit_password_and_csrf(self):
        self.client.force_login(self.admin)
        payload = self.post_data(email=self.worker.email, username=self.worker.username, employee_id=self.worker.employee_id, name="Renamed")
        response = self.client.post(reverse("accounts:employee-edit", args=[self.worker.pk]), payload)
        self.assertEqual(response.status_code, 302)
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.name, "Renamed")
        self.assertTrue(self.worker.check_password(PASSWORD))
        url = reverse("accounts:employee-password", args=[self.worker.pk])
        self.assertEqual(self.client.post(url, {"password1": NEW_PASSWORD, "password2": "Mismatch"}).status_code, 200)
        self.assertEqual(self.client.post(url, {"password1": NEW_PASSWORD, "password2": NEW_PASSWORD}).status_code, 302)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.admin)
        self.assertEqual(csrf.post(url, {"password1": PASSWORD, "password2": PASSWORD}).status_code, 403)

    def test_anonymous_partner_and_leader_reset_denied(self):
        self.assertEqual(self.client.get(reverse("accounts:employee-list")).status_code, 302)
        self.client.force_login(self.partner)
        self.assertEqual(self.client.get(reverse("accounts:employee-list")).status_code, 403)
        self.client.force_login(self.leader)
        self.assertEqual(self.client.post(reverse("accounts:employee-password", args=[self.worker.pk]), {"password1": NEW_PASSWORD, "password2": NEW_PASSWORD}).status_code, 403)
        self.assertEqual(self.client.post(reverse("accounts:employee-edit", args=[self.other.pk]), self.post_data()).status_code, 404)

    def test_employee_management_scope_and_no_separate_section(self):
        self.client.force_login(self.leader)
        response = self.client.get(reverse("accounts:employee-detail", args=[self.worker.pk]))
        self.assertContains(response, "Edit employee")
        self.assertNotContains(response, self.worker.password)
        self.assertNotContains(response, "> Counsellors</a>")
        self.assertNotContains(self.client.get(reverse("accounts:employee-list")), "South Counsellor")
        self.assertNotIn(Counsellor, admin.site._registry)
        request = RequestFactory().get("/admin/")
        request.user = self.leader
        self.assertFalse(admin.site._registry[CounsellorHistory].has_view_permission(request, self.other.counsellor_history.first()))
        self.assertEqual(self.client.get("/accounts/counsellors/").status_code, 404)

    def test_employee_filter_by_role_and_block_action(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("accounts:employee-list"), {"role": "COUNSELLOR"})
        self.assertEqual(response.context["page_obj"].paginator.count, 2)
        self.assertNotContains(response, "Other leader")
        response = self.client.post(reverse("accounts:employee-status", args=[self.worker.pk]), {"action": "block"})
        self.assertRedirects(response, reverse("accounts:employee-detail", args=[self.worker.pk]))
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.account_status, "BLOCKED")
        self.assertFalse(self.worker.is_active)
        self.assertEqual(self.worker.counsellor_history.first().changes["account_status"]["after"], "BLOCKED")

    def test_team_leader_cannot_inject_employee_role(self):
        self.client.force_login(self.leader)
        response = self.client.post(reverse("accounts:employee-create"), self.post_data(role="SUPER_ADMIN"))
        self.assertEqual(response.status_code, 302)
        target = User.objects.get(username="new.counsellor")
        self.assertEqual(target.role, "COUNSELLOR")
        self.assertFalse(target.is_staff or target.is_superuser)

    def test_legacy_employee_status_stays_synchronized(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("accounts:employee-status", args=[self.worker.pk]), {"action": "deactivate"})
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.account_status, "INACTIVE")
        self.client.post(reverse("accounts:employee-status", args=[self.worker.pk]), {"action": "activate"})
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.account_status, "ACTIVE")
