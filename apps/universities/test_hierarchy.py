from django.test import TestCase, override_settings
from django.urls import reverse
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient
from apps.accounts.models import User
from apps.partners.models import Partner
from apps.partners.services import submit_lead
from apps.leads.models import Lead
from apps.leads import services as lead_services
from apps.applications.models import Application
from apps.applications.services import save_application
from apps.courses.models import Course
from apps.partners.forms import SubmissionForm
from apps.applications.forms import ApplicationForm
from .models import Country, University


@override_settings(SECURE_SSL_REDIRECT=False)
class EducationHierarchyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("education-admin@example.com", name="Admin", role="ADMIN")
        cls.counsellor = User.objects.create_user("education-counsellor@example.com", name="Counsellor")
        cls.partner_user = User.objects.create_user("education-partner@example.com", name="Partner", role="PARTNER")
        cls.partner = Partner.objects.create(user=cls.partner_user, business_name="Test partner", contact_person="Partner", email=cls.partner_user.email,
            phone="9876543210", status="ACTIVE", created_by=cls.admin)
        cls.ca = Country.objects.create(name="Canada", code="CA")
        cls.uk = Country.objects.create(name="UK", code="UK")
        cls.disabled = Country.objects.create(name="Disabled", is_active=False)
        cls.uni = University.objects.create(name="Shared university", country=cls.ca)
        cls.other = University.objects.create(name="Shared university", country=cls.uk)
        cls.hidden = University.objects.create(name="Inactive university", country=cls.ca, is_active=False)
        cls.course = Course.objects.create(university=cls.uni, name="MSc Computing", program="MSc", duration_months=24, fees=12000,
            eligibility="Bachelor degree", mode="ON_CAMPUS", intake="September 2027")
        cls.other_course = Course.objects.create(university=cls.other, name="MBA", program="MBA", duration_months=12, fees=15000,
            eligibility="Bachelor degree", mode="ONLINE", intake="January 2027")

    def api(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def submission(self, **kwargs):
        return {"full_name": "Education student", "phone": "9876543211", "selected_country": self.ca.pk,
                "selected_university": self.uni.pk, "selected_course": self.course.pk, **kwargs}

    def test_country_api_crud_validation_and_pagination(self):
        api = self.api(self.admin)
        response = api.post("/api/v1/countries/", {"name": "Australia", "code": "au"})
        self.assertEqual(response.status_code, 201, response.data)
        pk = response.data["id"]
        self.assertEqual(response.data["code"], "AU")
        self.assertEqual(api.post("/api/v1/countries/", {"name": "australia"}).status_code, 400)
        self.assertEqual(api.post("/api/v1/countries/", {"name": "Different", "code": "AU"}).status_code, 400)
        self.assertEqual(api.patch(f"/api/v1/countries/{pk}/", {"name": "Australia updated"}).status_code, 200)
        self.assertEqual(api.get(f"/api/v1/countries/{pk}/").data["name"], "Australia updated")
        self.assertFalse(api.post(f"/api/v1/countries/{pk}/deactivate/").data["is_active"])
        self.assertTrue(api.post(f"/api/v1/countries/{pk}/activate/").data["is_active"])
        self.assertEqual(api.delete(f"/api/v1/countries/{pk}/").status_code, 405)
        Country.objects.bulk_create([Country(name=f"Page {i}") for i in range(28)])
        response = api.get("/api/v1/countries/?search=Page")
        self.assertEqual(response.data["count"], 28)
        self.assertIsNotNone(response.data["next"])
        self.assertEqual(api.get("/api/v1/countries/?is_active=wrong").status_code, 400)

    def test_master_api_hierarchy_and_scoped_uniqueness(self):
        api = self.api(self.admin)
        response = api.get(f"/api/v1/universities/?country={self.ca.pk}")
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(api.get("/api/v1/universities/?country=bad").status_code, 400)
        response = api.post("/api/v1/universities/", {"name": "New college", "country": self.ca.pk})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["country_name"], "Canada")
        self.assertEqual(api.post("/api/v1/universities/", {"name": "new college", "country": self.ca.pk}).status_code, 400)
        self.assertEqual(api.post("/api/v1/universities/", {"name": "New college", "country": self.uk.pk}).status_code, 201)
        self.assertEqual(api.post("/api/v1/universities/", {"name": "Invalid", "country": self.disabled.pk}).status_code, 400)
        self.assertEqual(api.post("/api/v1/universities/", {"name": "Missing"}).status_code, 400)
        response = api.get(f"/api/v1/courses/?university={self.uni.pk}&country={self.ca.pk}")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["country_name"], "Canada")
        self.assertEqual(api.get(f"/api/v1/courses/?university={self.uni.pk}&country={self.uk.pk}").data["count"], 0)

    def test_master_api_permissions_and_authentication(self):
        anonymous = APIClient()
        for path in ("/api/v1/countries/", "/api/v1/universities/", "/api/v1/courses/", "/api/v1/education/countries/"):
            self.assertEqual(anonymous.get(path).status_code, 401)
        for user in (self.counsellor, self.partner_user):
            api = self.api(user)
            for kind, obj in (("countries", self.ca), ("universities", self.uni), ("courses", self.course)):
                self.assertEqual(api.post(f"/api/v1/{kind}/", {}).status_code, 403)
                self.assertEqual(api.patch(f"/api/v1/{kind}/{obj.pk}/", {"name": "Changed"}).status_code, 403)
                self.assertEqual(api.post(f"/api/v1/{kind}/{obj.pk}/deactivate/").status_code, 403)
        self.assertEqual(self.api(self.counsellor).get("/api/v1/countries/").status_code, 200)

    def test_partner_active_choices_and_read_only(self):
        api = self.api(self.partner_user)
        response = api.get("/api/v1/education/countries/")
        self.assertEqual({row["id"] for row in response.data["results"]}, {self.ca.pk, self.uk.pk})
        path = f"/api/v1/education/countries/{self.ca.pk}/universities/"
        self.assertEqual([row["id"] for row in api.get(path).data["results"]], [self.uni.pk])
        path = f"/api/v1/education/universities/{self.uni.pk}/courses/"
        self.assertEqual(api.get(path).data["results"][0]["id"], self.course.pk)
        self.assertEqual(api.post(path, {}).status_code, 405)
        Course.objects.filter(pk=self.course.pk).update(intake_status="CLOSED")
        self.assertEqual(api.get(path).data["count"], 0)
        self.ca.is_active = False
        self.ca.save()
        self.assertEqual(api.get(path).status_code, 404)
        self.assertEqual(api.get(f"/api/v1/education/countries/{self.ca.pk}/universities/").status_code, 404)
        self.partner.status = "PENDING"
        self.partner.save()
        self.assertEqual(api.get("/api/v1/education/countries/").status_code, 403)

    def test_session_partner_choices_and_boundary(self):
        self.client.force_login(self.partner_user)
        self.assertEqual(self.client.get("/api/v1/education/countries/").status_code, 200)
        self.assertEqual(self.client.get("/countries/").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/countries/").status_code, 403)

    def test_partner_api_valid_and_invalid_combinations(self):
        api = self.api(self.partner_user)
        url = reverse("partner-api:leads")
        for invalid in ({"selected_country": self.uk.pk}, {"selected_course": self.other_course.pk}, {"selected_country": 99999}):
            response = api.post(url, self.submission(**invalid))
            self.assertEqual(response.status_code, 400, response.data)
            self.assertFalse(Lead.objects.exists())
        response = api.post(url, self.submission())
        self.assertEqual(response.status_code, 201, response.data)
        lead = Lead.objects.get(pk=response.data["id"])
        self.assertEqual((lead.selected_country_id, lead.selected_university_id, lead.selected_course_id), (self.ca.pk, self.uni.pk, self.course.pk))
        self.assertEqual((lead.partner_id, lead.lead_source, lead.status), (self.partner.pk, "PARTNER", "NEW"))
        response = api.patch(reverse("partner-api:detail", args=[lead.pk]), {"selected_country": self.uk.pk})
        self.assertEqual(response.status_code, 400)
        self.assertIn("selected_university", response.data)
        self.ca.is_active = False
        self.ca.save()
        self.assertEqual(api.patch(reverse("partner-api:detail", args=[lead.pk]), {"full_name": "Retained selection"}).status_code, 200)

    def test_inactive_selections_rejected_on_new_transactions(self):
        api = self.api(self.partner_user)
        for model, pk in ((Country, self.ca.pk), (University, self.uni.pk), (Course, self.course.pk)):
            model.objects.filter(pk=pk).update(is_active=False)
            self.assertEqual(api.post(reverse("partner-api:leads"), self.submission()).status_code, 400)
            model.objects.filter(pk=pk).update(is_active=True)
        self.assertFalse(Lead.objects.exists())

    def test_dependent_forms_and_partner_web_submission(self):
        form = SubmissionForm(data={**self.submission(), "preferred_study_mode": "ON_CAMPUS"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(list(form.fields["selected_university"].queryset), [self.uni])
        self.assertEqual(list(form.fields["selected_course"].queryset), [self.course])
        bad = SubmissionForm(data={**self.submission(selected_country=self.uk.pk), "preferred_study_mode": "ON_CAMPUS"})
        self.assertFalse(bad.is_valid())
        self.client.force_login(self.partner_user)
        response = self.client.post(reverse("partner-portal:submit"), {**self.submission(), "preferred_study_mode": "ON_CAMPUS"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Lead.objects.get().selected_country_id, self.ca.pk)

    def test_country_web_management_and_filters(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("countries:create"), {"name": "Australia", "code": "AU", "is_active": "on"})
        self.assertEqual(response.status_code, 302)
        country = Country.objects.get(code="AU")
        self.assertContains(self.client.get(reverse("countries:list")), "Australia")
        self.assertEqual(self.client.post(reverse("countries:edit", args=[country.pk]), {"name": "Australia updated", "code": "AU", "is_active": "on"}).status_code, 302)
        self.assertEqual(self.client.post(reverse("countries:status", args=[country.pk]), {"action": "deactivate"}).status_code, 302)
        response = self.client.get(reverse("universities:list"), {"country": self.ca.pk})
        self.assertEqual(response.context["page_obj"].paginator.count, 2)
        self.assertEqual(self.client.get(reverse("countries:status", args=[country.pk])).status_code, 405)
        self.client.force_login(self.counsellor)
        self.assertEqual(self.client.post(reverse("countries:create"), {"name": "Denied"}).status_code, 403)

    def test_application_country_derived_and_inactive_protection(self):
        lead = lead_services.create_lead(self.admin, {"full_name": "Application student", "phone": "9876543299"}, counsellor=self.counsellor)
        data = {"university": self.uni, "course": self.course, "status": "DRAFT"}
        app = save_application(self.counsellor, data, lead_id=lead.pk)
        self.assertEqual(app.university.country, self.ca)
        bad = ApplicationForm(data={"lead": lead.pk, "country": self.uk.pk, "university": self.uni.pk, "course": self.course.pk, "status": "DRAFT"}, actor=self.counsellor)
        self.assertFalse(bad.is_valid())
        self.ca.is_active = False
        self.ca.save()
        with self.assertRaises(ValidationError):
            save_application(self.counsellor, data, lead_id=lead.pk)
        app = save_application(self.counsellor, {"remarks": "Historical offering retained"}, pk=app.pk)
        self.assertEqual(app.university_id, self.uni.pk)
        self.assertNotIn("country", [field.name for field in Application._meta.fields])

    def test_used_university_cannot_move_country(self):
        lead = submit_lead(self.partner_user, {"full_name": "Selected student", "phone": "9876543211", "selected_university": self.uni, "selected_course": self.course})
        self.assertEqual(lead.selected_country_id, self.ca.pk)
        api = self.api(self.admin)
        self.assertEqual(api.patch(f"/api/v1/universities/{self.uni.pk}/", {"country": self.uk.pk}).status_code, 400)

    def test_admin_pages_render_hierarchy_controls(self):
        root = User.objects.create_superuser("education-root@example.com", "Test-only-Cedar-97!", name="Root")
        self.client.force_login(root)
        for path in ("/admin/universities/country/add/", "/admin/universities/university/add/", "/admin/courses/course/add/", "/admin/applications/application/add/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            if "country/add" not in path:
                self.assertContains(response, 'name="country"')
        response = self.client.get("/admin/courses/course/add/")
        self.assertContains(response, "js/education.js")

    def test_course_master_api_crud_and_inactive_parent(self):
        api = self.api(self.admin)
        data = {"university": self.uni.pk, "name": "Data Science", "program": "MSc", "duration_months": 12,
            "fees": "20000.00", "currency": "CAD", "eligibility": "Degree", "mode": "ONLINE", "intake": "2028", "intake_status": "OPEN"}
        response = api.post("/api/v1/courses/", data)
        self.assertEqual(response.status_code, 201, response.data)
        pk = response.data["id"]
        self.assertEqual(api.patch(f"/api/v1/courses/{pk}/", {"intake_status": "UPCOMING"}).status_code, 200)
        self.assertFalse(api.post(f"/api/v1/courses/{pk}/deactivate/").data["is_active"])
        self.assertTrue(api.post(f"/api/v1/courses/{pk}/activate/").data["is_active"])
        self.assertEqual(api.post("/api/v1/courses/", {**data, "university": self.hidden.pk}).status_code, 400)
        self.ca.is_active = False
        self.ca.save()
        self.assertEqual(api.post("/api/v1/courses/", {**data, "name": "Another"}).status_code, 400)

    def test_partner_cannot_edit_other_partners_education(self):
        other_user = User.objects.create_user("other-education-partner@example.com", name="Other", role="PARTNER")
        other_partner = Partner.objects.create(user=other_user, business_name="Other partner", contact_person="Other", email=other_user.email,
            phone="9876543233", status="ACTIVE", created_by=self.admin)
        lead = submit_lead(other_user, {"full_name": "Other student", "phone": "9876543234"})
        response = self.api(self.partner_user).patch(reverse("partner-api:detail", args=[lead.pk]), self.submission())
        self.assertEqual(response.status_code, 404)
        lead.refresh_from_db()
        self.assertIsNone(lead.selected_country_id)
