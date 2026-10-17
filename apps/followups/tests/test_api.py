from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.followups.models import FollowUp
from apps.leads.models import Lead


PASSWORD = "Followup-Test-947!"


@override_settings(
    SECURE_SSL_REDIRECT=False,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class FollowUpAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            "admin-followup@example.com",
            PASSWORD,
            name="Admin",
            role="ADMIN",
            is_staff=True,
        )

        cls.counsellor = User.objects.create_user(
            "counsellor-followup@example.com",
            PASSWORD,
            name="Counsellor",
            role="COUNSELLOR",
        )

        cls.other_counsellor = User.objects.create_user(
            "other-followup@example.com",
            PASSWORD,
            name="Other Counsellor",
            role="COUNSELLOR",
        )

        cls.lead = Lead.objects.create(
            full_name="Followup Student",
            phone="9876543201",
            created_by=cls.admin,
            updated_by=cls.admin,
            assigned_counsellor=cls.counsellor,
        )

        cls.other_lead = Lead.objects.create(
            full_name="Other Student",
            phone="9876543202",
            created_by=cls.admin,
            updated_by=cls.admin,
            assigned_counsellor=cls.other_counsellor,
        )

    def setUp(self):
        self.client = APIClient()

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def create_followup(self, **overrides):
        data = {
            "lead": self.lead.pk,
            "assigned_to": self.counsellor.pk,
            "followup_type": "CALL",
            "scheduled_at": (
                timezone.now() + timedelta(hours=2)
            ).isoformat(),
            "notes": "Initial follow-up",
        }
        data.update(overrides)

        response = self.client.post(
            "/api/v1/followups/",
            data,
            format="json",
        )

        return response

    def test_unauthenticated_access_is_rejected(self):
        response = self.client.get("/api/v1/followups/")
        self.assertEqual(response.status_code, 401)

    def test_list_followups(self):
        self.authenticate(self.admin)

        FollowUp.objects.create(
            lead=self.lead,
            assigned_to=self.counsellor,
            created_by=self.admin,
            scheduled_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.get("/api/v1/followups/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)

    def test_create_followup(self):
        self.authenticate(self.admin)

        response = self.create_followup()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "SCHEDULED")
        self.assertEqual(
            response.data["lead"],
            self.lead.pk,
        )

        self.assertTrue(
            FollowUp.objects.filter(
                lead=self.lead,
                assigned_to=self.counsellor,
            ).exists()
        )

    def test_create_followup_with_past_time_is_rejected(self):
        self.authenticate(self.admin)

        response = self.create_followup(
            scheduled_at=(
                timezone.now() - timedelta(hours=1)
            ).isoformat()
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Follow-up time cannot be in the past.", str(response.data))

    def test_create_followup_with_invalid_assignee_is_rejected(self):
        self.authenticate(self.counsellor)

        response = self.create_followup(
            assigned_to=self.other_counsellor.pk
        )

        self.assertEqual(response.status_code, 400)

    def test_retrieve_followup(self):
        self.authenticate(self.admin)

        followup = FollowUp.objects.create(
            lead=self.lead,
            assigned_to=self.counsellor,
            created_by=self.admin,
            scheduled_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.get(
            f"/api/v1/followups/{followup.pk}/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], followup.pk)
        self.assertEqual(
            response.data["lead_name"],
            "Followup Student",
        )

    def test_update_scheduled_followup(self):
        self.authenticate(self.admin)

        followup = FollowUp.objects.create(
            lead=self.lead,
            assigned_to=self.counsellor,
            created_by=self.admin,
            scheduled_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.patch(
            f"/api/v1/followups/{followup.pk}/",
            {
                "followup_type": "WHATSAPP",
                "notes": "Updated notes",
                "scheduled_at": (
                    timezone.now() + timedelta(hours=3)
                ).isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["followup_type"], "WHATSAPP")
        self.assertEqual(response.data["notes"], "Updated notes")

    def test_complete_followup(self):
        self.authenticate(self.admin)

        followup = FollowUp.objects.create(
            lead=self.lead,
            assigned_to=self.counsellor,
            created_by=self.admin,
            scheduled_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.post(
            f"/api/v1/followups/{followup.pk}/complete/",
            {
                "outcome": "Student is interested",
                "notes": "Discussed MBA options.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "COMPLETED")
        self.assertEqual(
            response.data["outcome"],
            "Student is interested",
        )
        self.assertIsNotNone(response.data["completed_at"])

    def test_missed_followup(self):
        self.authenticate(self.admin)

        followup = FollowUp.objects.create(
            lead=self.lead,
            assigned_to=self.counsellor,
            created_by=self.admin,
            scheduled_at=timezone.now() - timedelta(hours=1),
        )

        response = self.client.post(
            f"/api/v1/followups/{followup.pk}/mark-missed/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "MISSED")

    def test_cancel_followup(self):
        self.authenticate(self.admin)

        followup = FollowUp.objects.create(
            lead=self.lead,
            assigned_to=self.counsellor,
            created_by=self.admin,
            scheduled_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.post(
            f"/api/v1/followups/{followup.pk}/cancel/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "CANCELLED")

    def test_delete_endpoint_cancels_followup(self):
        self.authenticate(self.admin)

        followup = FollowUp.objects.create(
            lead=self.lead,
            assigned_to=self.counsellor,
            created_by=self.admin,
            scheduled_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.delete(
            f"/api/v1/followups/{followup.pk}/"
        )

        self.assertEqual(response.status_code, 204)

        followup.refresh_from_db()
        self.assertEqual(
            followup.status,
            FollowUp.Status.CANCELLED,
        )

    def test_completed_followup_cannot_be_edited(self):
        self.authenticate(self.admin)

        followup = FollowUp.objects.create(
            lead=self.lead,
            assigned_to=self.counsellor,
            created_by=self.admin,
            scheduled_at=timezone.now() + timedelta(hours=1),
            status=FollowUp.Status.COMPLETED,
        )

        response = self.client.patch(
            f"/api/v1/followups/{followup.pk}/",
            {
                "notes": "Trying to change completed follow-up",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_today_endpoint(self):
        self.authenticate(self.admin)

        FollowUp.objects.create(
            lead=self.lead,
            assigned_to=self.counsellor,
            created_by=self.admin,
            scheduled_at=timezone.now(),
        )

        response = self.client.get(
            "/api/v1/followups/today/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_upcoming_endpoint(self):
        self.authenticate(self.admin)

        FollowUp.objects.create(
            lead=self.lead,
            assigned_to=self.counsellor,
            created_by=self.admin,
            scheduled_at=timezone.now() + timedelta(days=1),
        )

        response = self.client.get(
            "/api/v1/followups/upcoming/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_missed_endpoint(self):
        self.authenticate(self.admin)

        FollowUp.objects.create(
            lead=self.lead,
            assigned_to=self.counsellor,
            created_by=self.admin,
            scheduled_at=timezone.now() - timedelta(hours=2),
            status=FollowUp.Status.MISSED,
        )

        response = self.client.get(
            "/api/v1/followups/missed/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_counsellor_can_access_own_followup(self):
        self.authenticate(self.counsellor)

        followup = FollowUp.objects.create(
            lead=self.lead,
            assigned_to=self.counsellor,
            created_by=self.admin,
            scheduled_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.get(
            f"/api/v1/followups/{followup.pk}/"
        )

        self.assertEqual(response.status_code, 200)

    def test_counsellor_cannot_access_other_lead_followup(self):
        self.authenticate(self.counsellor)

        followup = FollowUp.objects.create(
            lead=self.other_lead,
            assigned_to=self.other_counsellor,
            created_by=self.admin,
            scheduled_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.get(
            f"/api/v1/followups/{followup.pk}/"
        )

        self.assertIn(response.status_code, (403, 404))

    def test_complete_missing_outcome_is_allowed(self):
        self.authenticate(self.admin)

        followup = FollowUp.objects.create(
            lead=self.lead,
            assigned_to=self.counsellor,
            created_by=self.admin,
            scheduled_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.post(
            f"/api/v1/followups/{followup.pk}/complete/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["status"],
            FollowUp.Status.COMPLETED,
        )