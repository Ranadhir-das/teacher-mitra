from datetime import timedelta
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import User, Team
from apps.partners import services as partners
from apps.leads import services
from apps.leads.models import Lead
from apps.followups.models import FollowUp


@override_settings(SECURE_SSL_REDIRECT=False)
class PartnerToCounsellorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("flow-admin@example.com", name="Admin", role="ADMIN")
        cls.leader = User.objects.create_user("flow-leader@example.com", name="Leader", role="TEAM_LEADER")
        cls.other_leader = User.objects.create_user("flow-other-leader@example.com", name="Other leader", role="TEAM_LEADER")
        cls.counsellor = User.objects.create_user("flow-counsellor@example.com", name="Counsellor")
        cls.other = User.objects.create_user("flow-other@example.com", name="Other counsellor")
        cls.team = Team.objects.create(name="Workflow team", leader=cls.leader)
        cls.team.members.add(cls.counsellor)
        cls.other_team = Team.objects.create(name="Other workflow team", leader=cls.other_leader)
        cls.other_team.members.add(cls.other)
        cls.partner = partners.register_partner({"business_name": "Workflow partner", "contact_person": "Partner",
            "email": "flow-partner@example.com", "phone": "9876543210", "partner_type": "INDIVIDUAL"}, "Cedar-River-Partner-97!")
        from apps.partners.test_support import prepared_submission
        prepared_submission(cls.partner, cls.admin)
        partners.review_registration(cls.admin, cls.partner.pk, approve=True)
        cls.partner.refresh_from_db()

    def as_user(self, user):
        self.client.force_login(user)

    def action(self, lead, action, data):
        return self.client.post(reverse("leads:action", args=[lead.pk, action]), data)

    def submitted(self):
        return partners.submit_lead(self.partner.user, {"full_name": "Workflow student", "phone": "9876543211"})

    def test_complete_web_workflow(self):
        self.as_user(self.partner.user)
        response = self.client.post(reverse("partner-portal:submit"), {"full_name": "Workflow student", "phone": "9876543211", "preferred_study_mode": "UNDECIDED"})
        lead = Lead.objects.get(full_name="Workflow student")
        self.assertRedirects(response, reverse("partner-portal:detail", args=[lead.pk]))
        self.assertEqual((lead.partner_id, lead.lead_source, lead.status), (self.partner.pk, "PARTNER", "NEW"))
        for actor in (self.admin, self.leader, self.other_leader):
            self.as_user(actor)
            self.assertContains(self.client.get(reverse("leads:list")), lead.full_name)
            self.assertEqual(self.client.get(reverse("leads:detail", args=[lead.pk])).status_code, 200)
        self.as_user(self.counsellor)
        self.assertEqual(self.client.get(reverse("leads:detail", args=[lead.pk])).status_code, 404)
        self.as_user(self.admin)
        self.assertEqual(self.action(lead, "note", {"note": "Reviewed student requirements"}).status_code, 302)
        self.assertEqual(self.action(lead, "assign", {"assigned_counsellor": self.counsellor.pk, "assigned_team": self.team.pk, "reason": "Review complete"}).status_code, 302)
        lead.refresh_from_db()
        self.assertEqual(lead.status, "ASSIGNED")
        self.assertEqual(lead.assignment_history.count(), 1)
        self.assertTrue(lead.status_history.filter(previous_status="NEW", new_status="ASSIGNED").exists())
        self.as_user(self.counsellor)
        self.assertContains(self.client.get(reverse("leads:list")), lead.full_name)
        for status in ("CONTACTED", "INTERESTED", "COUNSELLING", "COURSE_SELECTED", "APPLICATION_STARTED", "APPLICATION_SUBMITTED", "ADMISSION_CONFIRMED"):
            self.assertEqual(self.action(lead, "status", {"status": status}).status_code, 302)
        self.assertEqual(self.action(lead, "note", {"note": "Student discussed course options"}).status_code, 302)
        date = timezone.localtime(timezone.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(reverse("followups:create", args=[lead.pk]), {"assigned_to": self.counsellor.pk,
            "followup_type": "CALL", "scheduled_at": date, "notes": "Private callback notes"})
        self.assertEqual(response.status_code, 302)
        followup = FollowUp.objects.get(lead=lead)
        self.assertContains(self.client.get(reverse("followups:list")), lead.full_name)
        self.assertEqual(self.client.post(reverse("followups:complete", args=[followup.pk]), {"outcome": "Documents received", "notes": "Private completion"}).status_code, 302)
        response = self.client.get(reverse("leads:detail", args=[lead.pk]))
        titles = [item.title for item in response.context["activity"]]
        for title in ("Status changed", "Lead assigned", "Note added", "Follow-up scheduled", "Follow-up completed"):
            self.assertIn(title, titles)
        self.as_user(self.partner.user)
        response = self.client.get(reverse("partner-portal:detail", args=[lead.pk]))
        self.assertContains(response, "Admission confirmed")
        self.assertNotContains(response, "Private callback notes")
        self.assertNotContains(response, "Student discussed course options")
        self.assertEqual(self.client.get(reverse("followups:list")).status_code, 403)

    def test_cross_team_review_does_not_allow_mutations_or_followup_access(self):
        lead = self.submitted()
        services.assign_lead(self.admin, lead.pk, self.counsellor, self.team)
        from apps.followups.services import create_followup
        followup = create_followup(lead=lead, assigned_to=self.counsellor, created_by=self.counsellor,
            followup_type="CALL", scheduled_at=timezone.now() + timedelta(days=1))
        for actor in (self.other, self.other_leader):
            self.as_user(actor)
            self.assertNotContains(self.client.get(reverse("followups:list")), lead.full_name)
            for action in ("complete", "cancel"):
                self.assertEqual(self.client.post(reverse("followups:" + action, args=[followup.pk]), {}).status_code, 404)
            self.assertEqual(self.client.get(reverse("followups:create", args=[lead.pk])).status_code, 404)
            self.assertEqual(self.action(lead, "note", {"note": "Unauthorized"}).status_code, 404)
        self.as_user(self.other_leader)
        self.assertEqual(self.action(lead, "assign", {"assigned_counsellor": self.other.pk, "assigned_team": self.other_team.pk}).status_code, 404)
        self.as_user(self.counsellor)
        date = timezone.localtime(timezone.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(reverse("followups:create", args=[lead.pk]), {"assigned_to": self.other.pk, "followup_type": "CALL", "scheduled_at": date})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(FollowUp.objects.count(), 1)
        self.assertEqual(self.action(lead, "status", {"status": "ADMISSION_CONFIRMED"}).status_code, 200)
        lead.refresh_from_db()
        self.assertEqual(lead.status, "ASSIGNED")
        # Reassignment revokes the previous counsellor's follow-up access too.
        services.assign_lead(self.admin, lead.pk, self.other, self.other_team)
        self.assertEqual(self.client.post(reverse("followups:complete", args=[followup.pk]), {}).status_code, 404)

    def test_partner_cannot_override_submission_ownership(self):
        self.as_user(self.partner.user)
        for field, value in (("status", "ADMISSION_CONFIRMED"), ("partner", "999"), ("lead_source", "WEBSITE"), ("assigned_counsellor", self.counsellor.pk)):
            response = self.client.post(reverse("partner-portal:submit"), {"full_name": "Tampered", "phone": "9876543211", "preferred_study_mode": "UNDECIDED", field: value})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(Lead.objects.exists())

    def test_team_leader_can_manage_own_team_and_team_only_assignment_stays_new(self):
        lead = self.submitted()
        services.assign_lead(self.admin, lead.pk, None, self.team)
        lead.refresh_from_db()
        self.assertEqual(lead.status, "NEW")
        self.as_user(self.leader)
        self.assertEqual(self.action(lead, "assign", {"assigned_counsellor": self.counsellor.pk, "assigned_team": self.team.pk}).status_code, 302)
        lead.refresh_from_db()
        self.assertEqual(lead.status, "ASSIGNED")
        self.assertEqual(lead.assignment_history.count(), 2)
        self.assertEqual(self.action(lead, "note", {"note": "Team reviewed"}).status_code, 302)

    def test_followup_services_reject_inaccessible_and_archived_leads(self):
        from apps.followups.services import create_followup, complete_followup
        from django.http import Http404
        from django.core.exceptions import ValidationError
        lead = self.submitted()
        services.assign_lead(self.admin, lead.pk, self.counsellor, self.team)
        followup = create_followup(lead=lead, assigned_to=self.counsellor, created_by=self.counsellor,
            followup_type="CALL", scheduled_at=timezone.now() + timedelta(days=1))
        with self.assertRaises(Http404):
            complete_followup(followup=followup, actor=self.other)
        services.archive_lead(self.admin, lead.pk)
        with self.assertRaises(ValidationError):
            complete_followup(followup=followup, actor=self.counsellor)
        followup.refresh_from_db()
        self.assertEqual(followup.status, "SCHEDULED")
