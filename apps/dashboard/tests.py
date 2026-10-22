from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.leads.models import Lead
from apps.leads.services import create_lead


@override_settings(SECURE_SSL_REDIRECT=False)
class DashboardFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("dashboard-filter@example.invalid", name="Dashboard Admin", role="ADMIN")
        cls.recent = create_lead(cls.admin, {"full_name": "Recent Filter Lead", "phone": "12025550801"})
        cls.older = create_lead(cls.admin, {"full_name": "Older Filter Lead", "phone": "12025550802"})
        Lead.objects.filter(pk=cls.older.pk).update(created_at=timezone.now() - timedelta(days=40))

    def test_date_filters_change_lead_and_chart_data(self):
        self.client.force_login(self.admin)
        recent = self.client.get(reverse("dashboard:index"), {"period": "7d"})
        self.assertEqual(recent.context["cards"][0]["value"], 1)
        self.assertEqual(recent.context["status_chart_data"], [{"label": "New", "value": 1}])
        self.assertNotContains(recent, "Older Filter Lead")

        all_time = self.client.get(reverse("dashboard:index"), {"period": "all"})
        self.assertEqual(all_time.context["cards"][0]["value"], 2)
        self.assertEqual(len(all_time.context["trend_chart_data"]["labels"]), 6)

        invalid = self.client.get(reverse("dashboard:index"), {"period": "unknown"})
        self.assertEqual(invalid.context["period"], "month")
        self.assertEqual(invalid.context["cards"][0]["value"], 1)
