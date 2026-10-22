from datetime import timedelta
from io import StringIO
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from apps.accounts.models import Team, User
from .models import Lead, Tag
from . import services
from .permissions import visible_leads


@override_settings(SECURE_SSL_REDIRECT=False)
class LeadTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("lead-admin@example.invalid", name="Lead Admin", role="ADMIN")
        cls.root = User.objects.create_superuser("root-leads@example.invalid", name="Root")
        cls.leader = User.objects.create_user("leader-one@example.invalid", name="Leader One", role="TEAM_LEADER")
        cls.other_leader = User.objects.create_user("leader-two@example.invalid", name="Leader Two", role="TEAM_LEADER")
        cls.c1 = User.objects.create_user("c1@example.invalid", name="Counsellor One")
        cls.c2 = User.objects.create_user("c2@example.invalid", name="Counsellor Two")
        cls.c3 = User.objects.create_user("c3@example.invalid", name="Counsellor Three")
        cls.team = Team.objects.create(name="First team", leader=cls.leader)
        cls.team.members.set([cls.c1, cls.c2])
        cls.other_team = Team.objects.create(name="Second team", leader=cls.other_leader)
        cls.other_team.members.add(cls.c3)
        cls.tag = Tag.objects.create(name="MBA")
        cls.own = services.create_lead(cls.admin, {"full_name": "First Student", "phone": "12025550101", "email": "first@example.invalid", "desired_course": "MBA", "city": "Pune", "state": "Maharashtra", "lead_source": "FACEBOOK", "priority": "HIGH"}, counsellor=cls.c1, team=cls.team, tags=[cls.tag])
        cls.other = services.create_lead(cls.admin, {"full_name": "Private Student", "phone": "12025550102", "email": "private@example.invalid"}, counsellor=cls.c3, team=cls.other_team)
        cls.unassigned = services.create_lead(cls.admin, {"full_name": "Unassigned Student", "phone": "12025550103"})

    def api_as(self, user):
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION="Bearer " + str(RefreshToken.for_user(user).access_token))
        return api

    def test_creation_normalizes_contacts_and_records_initial_history(self):
        lead = services.create_lead(self.admin, {"full_name": "  New Student  ", "phone": "+1 (202) 555-0199", "email": "UPPER@EXAMPLE.INVALID"})
        self.assertEqual(lead.full_name, "New Student")
        self.assertEqual(lead.phone, "12025550199")
        self.assertEqual(lead.email, "upper@example.invalid")
        self.assertEqual(lead.status_history.get().new_status, "NEW")
        self.assertEqual(lead.created_by, self.admin)

    def test_invalid_lead_fields(self):
        for field, value in (("full_name", " "), ("phone", "abc"), ("phone", "123"), ("email", "bad"), ("passing_year", 1800), ("passing_year", 9999), ("percentage_or_cgpa", "101"), ("percentage_or_cgpa", "12/10"), ("percentage_or_cgpa", "NaN"), ("budget", -1), ("date_of_birth", timezone.localdate() + timedelta(days=1))):
            with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                services.create_lead(self.admin, {"full_name": "Invalid", "phone": "12025550190", field: value})
        for data in ({}, {"full_name": "Missing phone"}, {"phone": "12025550190"}):
            with self.assertRaises(ValidationError):
                services.create_lead(self.admin, data)

    def test_database_status_and_priority_constraints(self):
        for field in ("status", "priority"):
            with self.assertRaises(IntegrityError), transaction.atomic():
                Lead.objects.filter(pk=self.own.pk).update(**{field: "INVALID"})

    def test_assignment_and_reassignment_history(self):
        lead = services.assign_lead(self.admin, self.unassigned.pk, self.c1, self.team, "Initial owner")
        self.assertEqual(lead.status, "ASSIGNED")
        services.assign_lead(self.leader, lead.pk, self.c2, self.team, "Capacity")
        event = lead.assignment_history.last()
        self.assertEqual(event.previous_counsellor, self.c1)
        self.assertEqual(event.new_counsellor, self.c2)
        self.assertEqual(event.reason, "Capacity")
        self.assertEqual(event.assigned_by, self.leader)
        self.assertEqual(lead.assignment_history.count(), 2)
        services.assign_lead(self.leader, lead.pk, self.c2, self.team)
        self.assertEqual(lead.assignment_history.count(), 2)

    def test_unassignment_resets_assigned_status_with_history(self):
        lead = services.assign_lead(self.leader, self.own.pk, None, self.team, "Return to queue")
        self.assertEqual(lead.status, "NEW")
        self.assertEqual(lead.status_history.last().new_status, "NEW")

    def test_team_assignment_boundaries(self):
        with self.assertRaises(PermissionDenied):
            services.assign_lead(self.leader, self.own.pk, self.c3, self.other_team)
        with self.assertRaises(ValidationError):
            services.assign_lead(self.admin, self.own.pk, self.c3, self.team)
        with self.assertRaises(PermissionDenied):
            services.assign_lead(self.c1, self.own.pk, self.c2, self.team)
        self.c2.is_active = False
        self.c2.save()
        with self.assertRaises(ValidationError):
            services.assign_lead(self.admin, self.own.pk, self.c2, self.team)

    def test_explicit_counsellor_assignment_permission_remains_scoped(self):
        self.c1.user_permissions.add(Permission.objects.get(codename="reassign_lead"))
        lead = services.assign_lead(self.c1, self.own.pk, self.c2, self.team, "Delegated")
        self.assertEqual(lead.assigned_counsellor, self.c2)
        self.assertFalse(visible_leads(self.c1).filter(pk=lead.pk).exists())

    def test_leader_can_create_only_with_permitted_team(self):
        with self.assertRaises(PermissionDenied):
            services.create_lead(self.leader, {"full_name": "New", "phone": "12025550190"})
        lead = services.create_lead(self.leader, {"full_name": "New", "phone": "12025550190"}, team=self.team)
        self.assertIn(lead, visible_leads(self.leader))
        with self.assertRaises(PermissionDenied):
            services.create_lead(self.c1, {"full_name": "New", "phone": "12025550191"})

    def test_workflow_and_audit(self):
        for value in ("CONTACTED", "INTERESTED", "COUNSELLING", "COURSE_SELECTED", "APPLICATION_STARTED"):
            lead = services.change_status(self.c1, self.own.pk, value, "Discussed options")
            self.assertEqual(lead.status_history.last().new_status, value)
        self.assertIsNotNone(lead.last_contacted_at)
        count = lead.status_history.count()
        services.change_status(self.c1, lead.pk, "APPLICATION_STARTED")
        self.assertEqual(lead.status_history.count(), count)

    def test_invalid_transition_does_not_write_history(self):
        count = self.own.status_history.count()
        with self.assertRaises(ValidationError):
            services.change_status(self.c1, self.own.pk, "ADMISSION_CONFIRMED")
        self.own.refresh_from_db()
        self.assertEqual(self.own.status, "ASSIGNED")
        self.assertEqual(self.own.status_history.count(), count)
        services.change_status(self.admin, self.own.pk, "ADMISSION_CONFIRMED", "Administrator exception")
        self.assertEqual(self.own.status_history.last().note, "Administrator exception")

    def test_no_assigned_status_without_counsellor(self):
        with self.assertRaises(ValidationError):
            services.change_status(self.admin, self.unassigned.pk, "ASSIGNED")

    def test_notes_and_tags(self):
        entry = services.add_note(self.c1, self.own.pk, "  Requested MBA details.  ")
        self.assertEqual(entry.note, "Requested MBA details.")
        self.assertEqual(entry.created_by, self.c1)
        with self.assertRaises(ValidationError):
            services.add_note(self.c1, self.own.pk, " ")
        services.update_lead(self.c1, self.own.pk, {"career_goal": "Management"}, tags=[])
        self.assertEqual(self.own.tags.count(), 0)

    def test_duplicate_phone_email_and_alternate_warning(self):
        for data in ({"phone": "+1 (202) 555-0101"}, {"phone": "12025550190", "email": "FIRST@EXAMPLE.INVALID"}, {"phone": "12025550190", "alternate_phone": "12025550101"}):
            with self.subTest(data=data), self.assertRaises(services.DuplicateLeadError) as caught:
                services.create_lead(self.admin, {"full_name": "Duplicate", **data})
            self.assertEqual(caught.exception.matches[0]["id"], self.own.pk)
        lead = services.create_lead(self.admin, {"full_name": "Confirmed duplicate", "phone": self.own.phone}, confirm_duplicate=True)
        self.assertNotEqual(lead.pk, self.own.pk)

    def test_duplicate_warning_does_not_disclose_private_records(self):
        with self.assertRaises(services.DuplicateLeadError) as caught:
            services.create_lead(self.leader, {"full_name": "Possible match", "phone": self.other.phone}, team=self.team)
        self.assertEqual(caught.exception.matches, [])

    def test_edit_contact_duplicate_and_protected_fields(self):
        with self.assertRaises(services.DuplicateLeadError):
            services.update_lead(self.c1, self.own.pk, {"phone": self.other.phone}, confirm_duplicate=True)
        for field in ("status", "assigned_counsellor", "is_active", "created_by"):
            with self.assertRaises(ValidationError):
                services.update_lead(self.admin, self.own.pk, {field: None})

    def test_archival_is_reversible_and_preserves_history(self):
        with self.assertRaises(PermissionDenied):
            services.archive_lead(self.c1, self.own.pk)
        count = self.own.status_history.count()
        services.archive_lead(self.admin, self.own.pk)
        self.own.refresh_from_db()
        self.assertFalse(self.own.is_active)
        self.assertEqual(self.own.status_history.count(), count)
        self.assertIn("archived", self.own.notes.last().note)
        with self.assertRaises(ValidationError):
            services.add_note(self.admin, self.own.pk, "Not allowed on archive")
        services.archive_lead(self.admin, self.own.pk, active=True)
        self.own.refresh_from_db()
        self.assertTrue(self.own.is_active)

    def test_bulk_assignment_history_for_each_lead(self):
        services.bulk_update(self.admin, [self.own.pk, self.unassigned.pk], "assign", counsellor=self.c2, team=self.team, reason="Batch")
        for lead in (self.own, self.unassigned):
            lead.refresh_from_db()
            self.assertEqual(lead.assigned_counsellor, self.c2)
            self.assertEqual(lead.assignment_history.last().reason, "Batch")

    def test_bulk_status_atomic_rollback(self):
        new = services.create_lead(self.admin, {"full_name": "Team queue", "phone": "12025550190"}, team=self.team)
        before = self.own.status_history.count()
        with self.assertRaises(ValidationError):
            services.bulk_update(self.leader, [self.own.pk, new.pk], "status", status="CONTACTED")
        self.own.refresh_from_db()
        self.assertEqual(self.own.status, "ASSIGNED")
        self.assertEqual(self.own.status_history.count(), before)

    def test_bulk_private_ids_reject_entire_batch(self):
        with self.assertRaises(PermissionDenied):
            services.bulk_update(self.c1, [self.own.pk, self.other.pk], "status", status="CONTACTED")
        self.own.refresh_from_db()
        self.assertEqual(self.own.status, "ASSIGNED")

    def test_web_auth_and_detail_scope(self):
        self.assertEqual(self.client.get("/leads/").status_code, 302)
        for user, count in ((self.admin, 3), (self.root, 3), (self.leader, 1), (self.c1, 1)):
            self.client.force_login(user)
            response = self.client.get("/leads/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["page_obj"].paginator.count, count)
        self.assertEqual(self.client.get(f"/leads/{self.other.pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"/leads/{self.other.pk}/edit/").status_code, 404)
        self.assertEqual(self.client.get("/leads/new/").status_code, 403)

    def test_web_pages_render_and_protect_actions(self):
        self.client.force_login(self.admin)
        for path in ("/leads/", "/students/", "/leads/new/", "/leads/tags/", f"/leads/{self.own.pk}/", f"/leads/{self.own.pk}/edit/", f"/leads/{self.own.pk}/assign/", f"/leads/{self.own.pk}/status/", f"/leads/{self.own.pk}/note/", f"/leads/{self.own.pk}/archive/", "/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
        self.client.force_login(self.c1)
        for action in ("assign", "archive"):
            self.assertEqual(self.client.post(f"/leads/{self.own.pk}/{action}/", {}).status_code, 403)
        self.assertEqual(self.client.get("/leads/tags/").status_code, 403)

    def test_web_create_edit_duplicate_and_notes(self):
        self.client.force_login(self.admin)
        data = {"full_name": "Web Student", "phone": "12025550190", "priority": "HIGH", "lead_source": "WEBSITE", "preferred_study_mode": "ONLINE"}
        response = self.client.post("/leads/new/", data)
        self.assertEqual(response.status_code, 302)
        lead = Lead.objects.get(full_name="Web Student")
        data["full_name"] = "Edited Student"
        self.assertEqual(self.client.post(f"/leads/{lead.pk}/edit/", data).status_code, 302)
        response = self.client.post("/leads/new/", data)
        self.assertContains(response, "Possible duplicate lead found")
        data["confirm_duplicate"] = "on"
        self.assertEqual(self.client.post("/leads/new/", data).status_code, 302)
        self.assertEqual(self.client.post(f"/leads/{lead.pk}/note/", {"note": "Web note"}).status_code, 302)
        self.assertEqual(lead.notes.get().note, "Web note")

    def test_bulk_web_confirmation_has_no_early_mutation(self):
        self.client.force_login(self.admin)
        response = self.client.post("/leads/bulk/", {"selected": [self.own.pk], "operation": "status"})
        self.assertContains(response, "Confirm and apply")
        self.own.refresh_from_db()
        self.assertEqual(self.own.status, "ASSIGNED")
        response = self.client.post("/leads/bulk/", {"confirm": "yes", "ids": str(self.own.pk), "operation": "status", "status": "CONTACTED"})
        self.assertEqual(response.status_code, 302)
        self.own.refresh_from_db()
        self.assertEqual(self.own.status, "CONTACTED")

    def test_web_csrf_required(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(f"/leads/{self.own.pk}/note/", {"note": "Bad"}).status_code, 403)

    def test_api_unauthenticated_and_private_actions(self):
        api = APIClient()
        self.assertEqual(api.get("/api/v1/leads/").status_code, 401)
        api = self.api_as(self.c1)
        for suffix in ("", "history/", "notes/"):
            self.assertEqual(api.get(f"/api/v1/leads/{self.other.pk}/{suffix}").status_code, 404)
        for suffix, payload in (("status/", {"status": "CONTACTED"}), ("notes/", {"note": "No"}), ("assign/", {"assigned_counsellor": self.c1.pk, "assigned_team": self.team.pk})):
            self.assertEqual(api.post(f"/api/v1/leads/{self.other.pk}/{suffix}", payload, format="json").status_code, 404)
        self.assertEqual(api.patch(f"/api/v1/leads/{self.other.pk}/", {"full_name": "No"}).status_code, 404)
        self.assertEqual(api.delete(f"/api/v1/leads/{self.other.pk}/").status_code, 404)

    def test_api_list_my_and_team_scope(self):
        for user, count in ((self.admin, 3), (self.leader, 1), (self.c1, 1)):
            api = self.api_as(user)
            self.assertEqual(api.get("/api/v1/leads/").data["count"], count)
        api = self.api_as(self.c1)
        response = api.get("/api/v1/leads/my/")
        self.assertEqual([row["id"] for row in response.data["results"]], [self.own.pk])
        response = api.get(f"/api/v1/leads/my/?assigned_to={self.c3.pk}")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.api_as(self.admin).get("/api/v1/leads/my/").data["count"], 0)

    def test_api_create_patch_and_response_shape(self):
        api = self.api_as(self.admin)
        response = api.post("/api/v1/leads/", {"full_name": "API Student", "phone": "12025550190", "assigned_counsellor": self.c1.pk, "assigned_team": self.team.pk, "tags": [self.tag.pk]}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["assigned_counsellor"], {"id": self.c1.pk, "name": self.c1.name})
        self.assertEqual(response.data["status_display"], "Assigned")
        self.assertNotIn("password", str(response.data))
        pk = response.data["id"]
        api = self.api_as(self.c1)
        response = api.patch(f"/api/v1/leads/{pk}/", {"city": "Jaipur", "tags": []}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["city"], "Jaipur")
        for field, value in (("status", "LOST"), ("assigned_counsellor", self.c2.pk), ("is_active", False), ("created_by", self.c1.pk)):
            self.assertEqual(api.patch(f"/api/v1/leads/{pk}/", {field: value}, format="json").status_code, 400)
        self.assertEqual(api.post("/api/v1/leads/", {"full_name": "Denied", "phone": "12025550199"}).status_code, 403)

    def test_api_assignment_status_notes_history_and_archive(self):
        api = self.api_as(self.c1)
        own_url = f"/api/v1/leads/{self.own.pk}/"
        self.assertEqual(api.post(own_url + "assign/", {"assigned_counsellor": self.c2.pk, "assigned_team": self.team.pk}, format="json").status_code, 403)
        self.assertEqual(api.post(own_url + "status/", {"status": "ADMISSION_CONFIRMED"}).status_code, 400)
        self.assertEqual(api.post(own_url + "status/", {"status": "CONTACTED", "note": "Reached student"}).status_code, 200)
        self.assertEqual(api.post(own_url + "notes/", {"note": "Interested in MBA"}).status_code, 201)
        self.assertEqual(api.get(own_url + "notes/").data["count"], 1)
        self.assertEqual(api.get(own_url + "history/").data["statuses"][-1]["new_status"], "CONTACTED")
        self.assertEqual(api.delete(own_url).status_code, 403)
        api = self.api_as(self.admin)
        self.assertEqual(api.post(own_url + "assign/", {"assigned_counsellor": self.c2.pk, "assigned_team": self.team.pk}, format="json").status_code, 200)
        self.assertEqual(api.delete(own_url).status_code, 204)
        self.assertEqual(api.get("/api/v1/leads/?activity=archived").data["count"], 1)
        self.assertEqual(api.patch(own_url, {"full_name": "Blocked"}).status_code, 400)
        self.assertEqual(api.post(own_url + "restore/").status_code, 200)

    def test_api_validation_and_duplicate_response(self):
        api = self.api_as(self.admin)
        for data in ({}, {"full_name": "Bad", "phone": "invalid"}, {"full_name": "Bad", "phone": "12025550199", "passing_year": 9999}):
            self.assertEqual(api.post("/api/v1/leads/", data).status_code, 400)
        payload = {"full_name": "Duplicate", "phone": self.own.phone}
        response = api.post("/api/v1/leads/", payload)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "possible_duplicate")
        payload["confirm_duplicate"] = True
        self.assertEqual(api.post("/api/v1/leads/", payload, format="json").status_code, 201)

    def test_combined_search_filters_and_ordering(self):
        api = self.api_as(self.admin)
        today = timezone.localdate().isoformat()
        response = api.get("/api/v1/leads/", {"search": "First", "status": "ASSIGNED", "priority": "HIGH", "assigned_to": self.c1.pk, "lead_source": "FACEBOOK", "city": "Pune", "state": "Maharashtra", "created_from": today, "created_to": today})
        self.assertEqual(response.data["count"], 1)
        for search in ("First", "+1 (202) 555-0101", "first@example.invalid"):
            self.assertEqual(api.get("/api/v1/leads/", {"search": search}).data["count"], 1)
        services.update_lead(self.admin, self.own.pk, {"alternate_phone": "12025550188"})
        self.assertEqual(api.get("/api/v1/leads/?search=12025550188").data["count"], 1)
        response = api.get("/api/v1/leads/?sort=priority")
        self.assertEqual(response.data["results"][0]["id"], self.own.pk)
        self.assertEqual(api.get("/api/v1/leads/?sort=oldest").data["results"][0]["id"], self.own.pk)
        for query in ("status=bad", "page_size=999", "created_from=bad", "created_from=2025-01-02&created_to=2025-01-01", "sort=;drop"):
            self.assertEqual(api.get("/api/v1/leads/?" + query).status_code, 400)

    def test_pagination(self):
        for i in range(21):
            services.create_lead(self.admin, {"full_name": f"Page Lead {i}", "phone": f"120255502{i:02d}"})
        api = self.api_as(self.admin)
        response = api.get("/api/v1/leads/")
        self.assertEqual(len(response.data["results"]), 20)
        self.assertIsNotNone(response.data["next"])
        self.assertEqual(len(api.get("/api/v1/leads/?page_size=50").data["results"]), 24)
        self.assertEqual(len(api.get("/api/v1/leads/?page=2").data["results"]), 4)

    def test_dashboard_and_students_are_scoped(self):
        services.change_status(self.admin, self.other.pk, "ADMISSION_CONFIRMED")
        self.client.force_login(self.c1)
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.context["cards"][0]["value"], 1)
        self.assertNotContains(response, self.other.full_name)
        self.assertEqual(self.client.get("/students/").context["page_obj"].paginator.count, 0)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/students/").context["page_obj"].paginator.count, 1)

    def test_csv_export_is_authenticated_scoped_and_formula_safe(self):
        from django.utils.http import urlencode

        url = reverse("leads:export")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.leader)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        body = b"".join(response.streaming_content).decode("utf-8-sig")
        self.assertIn("First Student", body)
        self.assertNotIn("Private Student", body)

        self.client.force_login(self.admin)
        Lead.objects.filter(pk=self.own.pk).update(full_name=" \t=1+1")
        response = self.client.get(url + "?" + urlencode({"search": "=1+1"}))
        body = b"".join(response.streaming_content).decode("utf-8-sig")
        self.assertIn("' \t=1+1", body)

    def test_admin_is_read_only_for_audited_models(self):
        self.client.force_login(self.root)
        for model in ("lead", "leadassignment", "leadstatushistory", "leadnote", "tag"):
            self.assertEqual(self.client.get(f"/admin/leads/{model}/").status_code, 200)
        self.assertEqual(self.client.get(f"/admin/leads/lead/{self.own.pk}/change/").status_code, 200)
        self.assertEqual(self.client.post(f"/admin/leads/lead/{self.own.pk}/change/", {"status": "LOST"}).status_code, 403)
        self.assertEqual(self.client.get(f"/admin/leads/lead/{self.own.pk}/delete/").status_code, 403)

    def test_tags_case_insensitive_and_admin_managed(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post("/leads/tags/", {"name": "Online"}).status_code, 302)
        self.assertTrue(Tag.objects.filter(name="ONLINE").exists())
        self.assertContains(self.client.post("/leads/tags/", {"name": "online"}), "already exists")
        self.assertEqual(self.api_as(self.c1).get("/api/v1/tags/").status_code, 200)

    def test_demo_command_is_idempotent_and_has_no_usable_passwords(self):
        output = StringIO()
        call_command("seed_demo", stdout=output)
        self.assertEqual(Lead.objects.filter(email__contains="alp-demo-student").count(), 20)
        count = Lead.objects.count()
        call_command("seed_demo", stdout=output)
        self.assertEqual(Lead.objects.count(), count)
        for user in User.objects.filter(email__startswith="alp-demo-"):
            self.assertFalse(user.has_usable_password())

    def test_api_rejects_non_object_json_without_server_error(self):
        api = self.api_as(self.admin)
        for data in ([{"full_name": "Invalid shape"}], "text", 42):
            self.assertEqual(api.post("/api/v1/leads/", data, format="json").status_code, 400)

    def test_bulk_assignment_failure_rolls_back_all_audit_writes(self):
        prior_count = self.own.assignment_history.count()
        with self.assertRaises(ValidationError):
            services.bulk_update(self.admin, [self.own.pk, self.unassigned.pk], "assign", counsellor=self.c3, team=self.team)
        self.own.refresh_from_db()
        self.assertEqual(self.own.assigned_counsellor, self.c1)
        self.assertEqual(self.own.assignment_history.count(), prior_count)

    def test_bulk_status_records_each_change(self):
        services.bulk_update(self.admin, [self.own.pk, self.other.pk], "status", status="CONTACTED", note="Bulk contact review")
        for lead in (self.own, self.other):
            self.assertEqual(lead.status_history.last().new_status, "CONTACTED")
            self.assertEqual(lead.status_history.last().note, "Bulk contact review")

    def test_api_leader_cannot_transfer_outside_team(self):
        api = self.api_as(self.leader)
        response = api.post(f"/api/v1/leads/{self.own.pk}/assign/", {"assigned_counsellor": self.c3.pk, "assigned_team": self.other_team.pk}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(api.get(f"/api/v1/leads/{self.other.pk}/").status_code, 404)

    def test_list_query_count_does_not_grow_per_lead(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        api = self.api_as(self.admin)
        with CaptureQueriesContext(connection) as small:
            self.assertEqual(api.get("/api/v1/leads/").status_code, 200)
        for i in range(6):
            services.create_lead(self.admin, {"full_name": f"Efficiency {i}", "phone": f"120255503{i:02d}"}, counsellor=self.c1, team=self.team, tags=[self.tag])
        with CaptureQueriesContext(connection) as larger:
            self.assertEqual(api.get("/api/v1/leads/").status_code, 200)
        self.assertEqual(len(small), len(larger))

    def test_inactive_team_revokes_leader_access(self):
        self.team.is_active = False
        self.team.save()
        self.assertFalse(visible_leads(self.leader).exists())
        self.assertEqual(self.api_as(self.leader).get(f"/api/v1/leads/{self.own.pk}/").status_code, 404)

    def test_archived_duplicate_still_warns(self):
        services.archive_lead(self.admin, self.own.pk)
        with self.assertRaises(services.DuplicateLeadError):
            services.create_lead(self.admin, {"full_name": "Archive match", "phone": self.own.phone})

    def test_web_status_assignment_archive_posts(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(f"/leads/{self.own.pk}/assign/", {"assigned_counsellor": self.c2.pk, "assigned_team": self.team.pk, "reason": "Web reassignment"}).status_code, 302)
        self.assertEqual(self.client.post(f"/leads/{self.own.pk}/status/", {"status": "CONTACTED", "note": "Web transition"}).status_code, 302)
        self.assertEqual(self.client.post(f"/leads/{self.own.pk}/archive/", {"action": "archive"}).status_code, 302)
        self.own.refresh_from_db()
        self.assertFalse(self.own.is_active)
        self.assertEqual(self.own.assigned_counsellor, self.c2)
        self.assertEqual(self.own.status, "CONTACTED")
        self.assertEqual(self.client.post(f"/leads/{self.own.pk}/archive/", {"action": "restore"}).status_code, 302)

    def test_tag_rename_propagates_without_duplicate_records(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(f"/leads/tags/{self.tag.pk}/", {"name": "MBA_INTEREST"}).status_code, 302)
        self.assertEqual(self.own.tags.get().name, "MBA_INTEREST")

    def test_api_edit_email_duplicate_warns(self):
        api = self.api_as(self.admin)
        response = api.patch(f"/api/v1/leads/{self.own.pk}/", {"email": self.other.email}, format="json")
        self.assertEqual(response.status_code, 409)
        self.own.refresh_from_db()
        self.assertNotEqual(self.own.email, self.other.email)
        response = api.patch(f"/api/v1/leads/{self.own.pk}/", {"email": self.other.email, "confirm_duplicate": True}, format="json")
        self.assertEqual(response.status_code, 200)
