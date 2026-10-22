import csv
from io import StringIO

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Team, User
from apps.leads import services as lead_services


@override_settings(SECURE_SSL_REDIRECT=False)
class ReportAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("report-admin@example.invalid", name="Report Admin", role="ADMIN")
        cls.leader = User.objects.create_user("report-leader@example.invalid", name="Leader", role="TEAM_LEADER")
        cls.other_leader = User.objects.create_user("report-other@example.invalid", name="Other Leader", role="TEAM_LEADER")
        cls.counsellor = User.objects.create_user("report-counsellor@example.invalid", name="Counsellor", role="COUNSELLOR")
        cls.team = Team.objects.create(name="Report team", leader=cls.leader)
        cls.other_team = Team.objects.create(name="Other report team", leader=cls.other_leader)
        lead_services.create_lead(cls.admin, {"full_name": "Visible Report Lead", "phone": "12025550901"}, team=cls.team)
        lead_services.create_lead(cls.admin, {"full_name": "Private Report Lead", "phone": "12025550902"}, team=cls.other_team)

    def test_dashboard_filters_by_date_and_team_visibility(self):
        self.client.force_login(self.leader)
        response = self.client.get(reverse("reports:dashboard"), {"start_date": "2020-01-01", "end_date": "2099-01-01"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visible Report Lead")
        self.assertNotContains(response, "Private Report Lead")
        self.assertEqual(response.context["lead_report"]["total"], 1)

    def test_anonymous_requests_are_redirected_to_login(self):
        for name in ("reports:dashboard", "reports:leads-csv"):
            response = self.client.get(reverse(name))
            self.assertRedirects(response, f"/accounts/login/?next={reverse(name)}")

    def test_invalid_date_range_is_reported_and_csv_rejects_it(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("reports:dashboard"), {"start_date": "bad-date"})
        self.assertContains(response, "Enter a valid start date")
        self.assertEqual(response.context["lead_report"]["total"], 0)
        reversed_range = self.client.get(reverse("reports:dashboard"), {"start_date": "2025-01-02", "end_date": "2025-01-01"})
        self.assertEqual(reversed_range.context["lead_report"]["total"], 0)
        export = self.client.get(reverse("reports:leads-csv"), {"start_date": "bad-date"})
        self.assertEqual(export.status_code, 400)

    def test_csv_is_scoped_and_other_roles_cannot_export(self):
        self.client.force_login(self.leader)
        response = self.client.get(reverse("reports:leads-csv"))
        body = b"".join(response.streaming_content).decode()
        self.assertIn("Visible Report Lead", body)
        self.assertNotIn("Private Report Lead", body)
        self.client.force_login(self.counsellor)
        self.assertEqual(self.client.get(reverse("reports:leads-csv")).status_code, 403)

    def test_csv_escapes_spreadsheet_formulas_and_status_filter_applies(self):
        dangerous_values = ("=1+1", "+SUM(1,1)", "-1+1", "@SUM(1,1)", " \t=1+1", "\x00@SUM(1,1)")
        for index, value in enumerate(dangerous_values, 3):
            lead = lead_services.create_lead(self.admin, {"full_name": "Safe placeholder", "phone": f"120255509{index:02d}"})
            type(lead).objects.filter(pk=lead.pk).update(full_name=value)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("reports:leads-csv"), {"status": "NEW"})
        body = b"".join(response.streaming_content).decode()
        exported_names = {row[1] for row in list(csv.reader(StringIO(body)))[1:]}
        self.assertTrue({"'" + value for value in dangerous_values}.issubset(exported_names))
        filtered = self.client.get(reverse("reports:dashboard"), {"status": "LOST"})
        self.assertEqual(filtered.context["lead_report"]["total"], 0)
