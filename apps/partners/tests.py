from datetime import timedelta
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from apps.accounts.models import User
from apps.leads.models import Lead, LeadStatusHistory
from .models import Partner
from . import services
from .test_support import prepared_submission

PASSWORD = "Cedar-River-Partner-97!"


@override_settings(SECURE_SSL_REDIRECT=False)
class PartnerWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("admin@example.com", PASSWORD, name="Admin", role="ADMIN")
        cls.staff = User.objects.create_user("staff@example.com", PASSWORD, name="Counsellor")

    def signup_data(self, email="partner@example.com"):
        return {"business_name": "Learning Together", "contact_person": "Asha", "email": email,
                "phone": "9876543210", "partner_type": "INDIVIDUAL", "city": "Pune", "state": "Maharashtra"}

    def register(self, email="partner@example.com"):
        return services.register_partner(self.signup_data(email), PASSWORD)

    def approve(self, partner):
        prepared_submission(partner, self.admin)
        services.review_registration(self.admin, partner.pk, approve=True)
        partner.refresh_from_db()
        return User.objects.get(pk=partner.user_id)

    def test_public_signup(self):
        self.assertContains(self.client.get(reverse("partner-portal:signup")), "Become a partner")
        response = self.client.post(reverse("partner-portal:signup"), {**self.signup_data("Partner@Example.com"), "password": PASSWORD, "password_confirm": PASSWORD})
        self.assertRedirects(response, reverse("accounts:login"))
        partner = Partner.objects.get()
        self.assertEqual(partner.status, "REGISTERED")
        self.assertEqual(partner.user.email, "partner@example.com")
        self.assertEqual(partner.created_by_id, partner.user_id)
        self.assertEqual(partner.user.role, "PARTNER")
        self.assertTrue(partner.user.is_active)
        self.assertFalse(partner.user.is_staff or partner.user.is_superuser)
        self.assertTrue(partner.user.check_password(PASSWORD))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_signup_validation_and_tampering(self):
        valid = {**self.signup_data(), "password": PASSWORD, "password_confirm": PASSWORD}
        for changes in ({"password_confirm": "mismatch"}, {"password": "123", "password_confirm": "123"},
                        {"email": "bad"}, {"phone": "abc"}, {"business_name": " "}, {"role": "ADMIN"}, {"status": "ACTIVE"}):
            with self.subTest(changes=changes):
                response = self.client.post(reverse("partner-portal:signup"), {**valid, **changes})
                self.assertEqual(response.status_code, 200)
                self.assertFalse(Partner.objects.exists())
        self.register()
        response = self.client.post(reverse("partner-portal:signup"), {**valid, "email": "PARTNER@example.com"})
        self.assertContains(response, "already exists")
        self.assertEqual(Partner.objects.count(), 1)

    def test_registration_rolls_back_on_invalid_partner(self):
        with self.assertRaises(ValidationError):
            services.register_partner({**self.signup_data(), "business_name": ""}, PASSWORD)
        self.assertFalse(User.objects.filter(role="PARTNER").exists())

    def test_pending_and_rejected_cannot_login_or_access(self):
        partner = self.register()
        for status in ("PENDING", "SUSPENDED", "INACTIVE"):
            Partner.objects.filter(pk=partner.pk).update(status=status)
            # Even legacy active identities cannot bypass the status gate.
            User.objects.filter(pk=partner.user_id).update(is_active=True)
            user = User.objects.get(pk=partner.user_id)
            self.client.logout()
            response = self.client.post(reverse("accounts:login"), {"username": user.email, "password": PASSWORD})
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("_auth_user_id", self.client.session)
            self.client.force_login(user)
            for name in ("dashboard", "reports", "leads", "submit", "profile"):
                self.assertEqual(self.client.get(reverse("partner-portal:" + name)).status_code, 403)
            api = APIClient()
            api.force_authenticate(user)
            self.assertEqual(api.get(reverse("partner-api:leads")).status_code, 403)

    def test_admin_approval_and_approved_login(self):
        partner = self.register()
        prepared_submission(partner, self.admin)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("partners:list") + "?status=SUBMITTED"), partner.business_name)
        self.assertContains(self.client.get(reverse("partners:detail", args=[partner.pk])), "Review onboarding and documents")
        url = reverse("partners:approve", args=[partner.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertRedirects(self.client.post(url), reverse("partners:detail", args=[partner.pk]))
        partner.refresh_from_db()
        self.assertEqual(partner.status, "ACTIVE")
        self.assertTrue(partner.user.is_active)
        self.client.logout()
        self.assertRedirects(self.client.post(reverse("accounts:login"), {"username": partner.email, "password": PASSWORD, "next": "/"}), reverse("partner-portal:dashboard"))
        for name in ("dashboard", "reports", "leads", "submit", "profile"):
            self.assertEqual(self.client.get(reverse("partner-portal:" + name)).status_code, 200)
        self.assertEqual(self.client.get(reverse("partners:list")).status_code, 403)
        self.assertEqual(self.client.get("/admin/").status_code, 403)
        with self.assertRaises(ValidationError):
            services.review_registration(self.admin, partner.pk, approve=False)

    def test_admin_rejection_and_permissions(self):
        partner = self.register()
        prepared_submission(partner, self.admin)
        url = reverse("partners:reject", args=[partner.pk])
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(url).status_code, 403)
        with self.assertRaises(PermissionDenied):
            services.review_registration(self.staff, partner.pk, approve=True)
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.post(url), reverse("partners:detail", args=[partner.pk]))
        partner.refresh_from_db()
        self.assertEqual(partner.status, "REJECTED")
        self.assertTrue(partner.user.is_active)
        self.client.logout()
        self.assertTrue(self.client.login(email=partner.email, password=PASSWORD))
        services.account_access(self.admin, partner.pk, True)
        self.assertEqual(self.client.get(reverse("partner-portal:leads")).status_code, 403)

    def test_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse("partner-portal:signup"), {}).status_code, 403)
        partner = self.register()
        client.force_login(self.admin)
        for name in ("approve", "reject"):
            self.assertEqual(client.post(reverse("partners:" + name, args=[partner.pk])).status_code, 403)
        response = client.get(reverse("partners:detail", args=[partner.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.post(reverse("partners:approve", args=[partner.pk]), {"csrfmiddlewaretoken": client.cookies["csrftoken"].value}).status_code, 302)

    def test_lead_and_report_isolation(self):
        partner, other = self.register(), self.register("other@example.com")
        user, other_user = self.approve(partner), self.approve(other)
        own = services.submit_lead(user, {"full_name": "Own Student", "phone": "9876543211"})
        foreign = services.submit_lead(other_user, {"full_name": "Private Other Student", "phone": "9876543212"})
        Lead.objects.filter(pk=foreign.pk).update(status="ADMISSION_CONFIRMED")
        LeadStatusHistory.objects.create(lead=own, new_status="CONTACTED", previous_status="NEW", changed_by=self.admin, note="Confidential staff note")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("partner-portal:detail", args=[foreign.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("partner-portal:edit", args=[foreign.pk]), {}).status_code, 404)
        for name in ("leads", "dashboard", "reports"):
            response = self.client.get(reverse("partner-portal:" + name) + f"?partner={other.pk}")
            self.assertContains(response, "Own Student")
            self.assertNotContains(response, "Private Other Student")
            self.assertNotContains(response, "Confidential staff note")
        response = self.client.get(reverse("partner-portal:reports"))
        self.assertEqual(response.context["report_total"], 1)
        self.assertEqual(response.context["trend_total"], 1)
        self.assertEqual(sum(row["value"] for row in response.context["status_rows"]), 1)
        self.assertTrue(all(item["lead_id"] == own.pk for item in response.context["activity"]))
        api = APIClient()
        api.force_authenticate(user)
        self.assertEqual(api.get(reverse("partner-api:detail", args=[foreign.pk])).status_code, 404)
        self.assertNotContains(api.get(reverse("partner-api:leads")), "Private Other Student")
        services.update_partner(self.admin, partner.pk, {"status": "SUSPENDED"})
        self.assertEqual(self.client.get(reverse("partner-portal:reports")).status_code, 302)

    def test_report_statuses_dates_and_empty_state(self):
        partner = self.register()
        user = self.approve(partner)
        self.client.force_login(user)
        response = self.client.get(reverse("partner-portal:reports"))
        self.assertContains(response, "No referrals yet")
        self.assertEqual(len(response.context["trend"]), 30)
        for status, label in Lead.Status.choices:
            Lead.objects.create(full_name=label, phone="9876543210", partner=partner, created_by=user, updated_by=user, status=status)
        old = partner.leads.first()
        Lead.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=40))
        response = self.client.get(reverse("partner-portal:reports"))
        self.assertEqual(response.context["report_total"], len(Lead.Status.choices))
        self.assertEqual(response.context["trend_total"], len(Lead.Status.choices) - 1)
        counts = {row["code"]: row["value"] for row in response.context["status_rows"]}
        self.assertEqual(counts["LOST"], 2)
        self.assertEqual(counts["APPLICATION_STARTED"], 1)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("partner-portal:reports")).status_code, 403)

    def test_status_changes_preserve_explicit_login_disable(self):
        partner = self.register()
        self.approve(partner)
        services.account_access(self.admin, partner.pk, False)
        services.update_partner(self.admin, partner.pk, {"status": "ACTIVE", "business_name": "Updated business"})
        self.assertFalse(User.objects.get(pk=partner.user_id).is_active)

    def test_api_login_follows_approval(self):
        from django.core.cache import cache
        cache.clear()
        partner = self.register()
        api = APIClient()
        url = reverse("auth-api:login")
        credentials = {"email": partner.email, "password": PASSWORD}
        self.assertEqual(api.post(url, credentials).status_code, 200)
        self.approve(partner)
        response = api.post(url, credentials)
        self.assertEqual(response.status_code, 200)
        api.credentials(HTTP_AUTHORIZATION="Bearer " + response.data["access"])
        self.assertEqual(api.get(reverse("partner-api:profile")).status_code, 200)
        services.update_partner(self.admin, partner.pk, {"status": "SUSPENDED"})
        self.assertEqual(api.get(reverse("partner-api:profile")).status_code, 401)
        api.credentials()
        self.assertEqual(api.post(url, credentials).status_code, 401)

    def test_student_logs_are_scoped_private_and_paginated(self):
        partner, other = self.register(), self.register("other@example.com")
        user, other_user = self.approve(partner), self.approve(other)
        own = services.submit_lead(user, {"full_name": "Own Student", "phone": "9876543211"})
        foreign = services.submit_lead(other_user, {"full_name": "Foreign Student", "phone": "9876543212"})
        for _ in range(21):
            LeadStatusHistory.objects.create(lead=own, previous_status="NEW", new_status="CONTACTED",
                changed_by=self.admin, note="Private counselling discussion")
        self.client.force_login(user)
        url = reverse("partner-portal:detail", args=[own.pk])
        response = self.client.get(url)
        self.assertContains(response, "Student logs")
        self.assertContains(response, "New &rarr; Contacted")
        self.assertNotContains(response, "Private counselling discussion")
        self.assertNotContains(response, self.admin.email)
        self.assertNotContains(response, "Foreign Student")
        self.assertEqual(len(response.context["student_logs"]), 20)
        self.assertContains(self.client.get(url + "?log_page=2"), "Student record created")
        self.assertEqual(self.client.get(reverse("partner-portal:detail", args=[foreign.pk])).status_code, 404)

    def test_student_without_status_events_has_creation_log(self):
        partner = self.register()
        user = self.approve(partner)
        lead = Lead.objects.create(full_name="Imported Student", phone="9876543210", partner=partner,
            created_by=self.admin, updated_by=self.admin)
        self.client.force_login(user)
        self.assertContains(self.client.get(reverse("partner-portal:detail", args=[lead.pk])), "Student record created")
