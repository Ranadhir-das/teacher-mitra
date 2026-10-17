from django.test import TestCase, Client, override_settings
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.urls import reverse
from rest_framework.test import APIClient
from apps.accounts.models import User
from apps.universities.models import Country, University
from apps.courses.models import Course
from apps.leads import services
from apps.leads.forms import LeadForm
from apps.leads.models import Lead


@override_settings(SECURE_SSL_REDIRECT=False)
class CatalogueTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("catalogue-admin@example.com", name="Admin", role="ADMIN")
        cls.counsellor = User.objects.create_user("catalogue-counsellor@example.com", name="Counsellor")
        cls.other = User.objects.create_user("catalogue-other@example.com", name="Other")
        cls.leader = User.objects.create_user("catalogue-leader@example.com", name="Leader", role="TEAM_LEADER")
        cls.partner = User.objects.create_user("catalogue-partner@example.com", name="Partner", role="PARTNER")
        cls.university = University.objects.create(country=Country.objects.get_or_create(name="Test Country")[0], name="North University")
        cls.other_university = University.objects.create(country=Country.objects.get_or_create(name="Test Country")[0], name="South University")
        cls.course = Course.objects.create(university=cls.university, name="Business Administration", program="MBA",
            duration_months=24, fees="120000.00", eligibility="Bachelor degree", mode="ONLINE", intake="July 2027")
        cls.lead = services.create_lead(cls.admin, {"full_name": "Catalogue student", "phone": "9876543210", "desired_course": "Original preference"}, counsellor=cls.counsellor)

    def course_data(self):
        return {"university": self.university.pk, "name": "Computer Applications", "program": "MCA",
            "duration_months": 24, "fees": "150000.00", "currency": "INR", "eligibility": "Graduate",
            "mode": "ONLINE", "intake": "August 2027", "intake_status": "OPEN", "is_active": "on"}

    def test_university_crud_and_status(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("universities:create"), {"name": "New University", "country": self.university.country_id, "is_active": "on"})
        obj = University.objects.get(name="New University")
        self.assertRedirects(response, reverse("universities:detail", args=[obj.pk]))
        response = self.client.post(reverse("universities:edit", args=[obj.pk]), {"name": "Updated University", "country": self.university.country_id, "is_active": "on"})
        self.assertEqual(response.status_code, 302)
        self.assertContains(self.client.get(reverse("universities:detail", args=[obj.pk])), "Updated University")
        for action, active in (("deactivate", False), ("activate", True)):
            self.assertEqual(self.client.post(reverse("universities:status", args=[obj.pk]), {"action": action}).status_code, 302)
            obj.refresh_from_db()
            self.assertEqual(obj.is_active, active)
        self.assertEqual(self.client.get(reverse("universities:status", args=[obj.pk])).status_code, 405)
        self.assertEqual(self.client.post(reverse("universities:status", args=[obj.pk]), {"action": "delete"}).status_code, 400)

    def test_course_crud(self):
        self.client.force_login(self.admin)
        data = self.course_data()
        response = self.client.post(reverse("courses:create"), data)
        obj = Course.objects.get(name=data["name"])
        self.assertRedirects(response, reverse("courses:detail", args=[obj.pk]))
        self.assertEqual(self.client.post(reverse("courses:edit", args=[obj.pk]), {**data, "fees": "160000.00"}).status_code, 302)
        self.assertContains(self.client.get(reverse("courses:detail", args=[obj.pk])), "160000.00")
        for action, active in (("deactivate", False), ("activate", True)):
            self.client.post(reverse("courses:status", args=[obj.pk]), {"action": action})
            obj.refresh_from_db()
            self.assertEqual(obj.is_active, active)

    def test_role_permissions(self):
        for user in (self.counsellor, self.leader):
            self.client.force_login(user)
            for namespace, obj in (("courses", self.course), ("universities", self.university)):
                for name, args in (("list", []), ("detail", [obj.pk])):
                    self.assertEqual(self.client.get(reverse(namespace + ":" + name, args=args)).status_code, 200)
                self.assertEqual(self.client.post(reverse(namespace + ":create"), {}).status_code, 403)
                self.assertEqual(self.client.post(reverse(namespace + ":edit", args=[obj.pk]), {}).status_code, 403)
                self.assertEqual(self.client.post(reverse(namespace + ":status", args=[obj.pk]), {"action": "deactivate"}).status_code, 403)
        self.client.force_login(self.partner)
        for namespace in ("courses", "universities"):
            self.assertEqual(self.client.get(reverse(namespace + ":list")).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("courses:list")).status_code, 302)

    def test_course_validation(self):
        self.client.force_login(self.admin)
        for invalid in ({"duration_months": 0}, {"fees": -1}, {"university": ""}, {"currency": "12X"}, {"mode": "INVALID"}, {"eligibility": ""}):
            with self.subTest(invalid=invalid):
                response = self.client.post(reverse("courses:create"), {**self.course_data(), **invalid})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(Course.objects.count(), 1)
        self.client.post(reverse("courses:create"), self.course_data())
        self.assertEqual(self.client.post(reverse("courses:create"), self.course_data()).status_code, 200)
        self.assertEqual(Course.objects.count(), 2)
        self.assertEqual(self.client.post(reverse("universities:create"), {"name": "north university", "country": self.university.country_id}).status_code, 200)
        self.assertEqual(University.objects.count(), 2)

    def test_search_filters_pagination(self):
        self.client.force_login(self.counsellor)
        response = self.client.get(reverse("courses:list"), {"search": "MBA", "university": self.university.pk, "mode": "ONLINE", "intake_status": "OPEN", "status": "active"})
        self.assertEqual(response.context["page_obj"].paginator.count, 1)
        self.assertEqual(self.client.get(reverse("courses:list"), {"university": "invalid"}).context["page_obj"].paginator.count, 0)
        self.assertEqual(self.client.get(reverse("courses:list"), {"mode": "ON_CAMPUS"}).context["page_obj"].paginator.count, 0)
        University.objects.bulk_create([University(name=f"Extra university {i}", country=self.university.country) for i in range(21)])
        response = self.client.get(reverse("universities:list"), {"search": "Extra", "page": 2})
        self.assertEqual(len(response.context["page_obj"]), 1)
        self.assertIn("search=Extra", response.context["query"])

    def test_counsellor_selection_and_audit(self):
        lead = services.update_lead(self.counsellor, self.lead.pk, {"selected_university": self.university, "selected_course": self.course})
        self.assertEqual(lead.selected_course, self.course)
        self.assertEqual(lead.desired_course, "Original preference")
        self.assertTrue(lead.notes.filter(note__contains="Counselling selection updated").exists())
        self.client.force_login(self.counsellor)
        self.assertContains(self.client.get(reverse("leads:detail", args=[lead.pk])), "Business Administration")
        self.assertContains(self.client.get(reverse("leads:edit", args=[lead.pk])), "selected_course")
        form = LeadForm(instance=lead, actor=self.counsellor)
        self.assertIn(self.course, form.fields["selected_course"].queryset)
        from django.http import Http404
        with self.assertRaises(Http404):
            services.update_lead(self.other, lead.pk, {"selected_course": self.course, "selected_university": self.university})

    def test_mismatched_or_unavailable_selection_rejected(self):
        with self.assertRaises(ValidationError):
            services.update_lead(self.counsellor, self.lead.pk, {"selected_university": self.other_university, "selected_course": self.course})
        with self.assertRaises(ValidationError):
            services.update_lead(self.counsellor, self.lead.pk, {"selected_course": self.course})
        for changes in ({"is_active": False}, {"is_active": True, "intake_status": "CLOSED"}):
            Course.objects.filter(pk=self.course.pk).update(**changes)
            self.course.refresh_from_db()
            with self.assertRaises(ValidationError):
                services.update_lead(self.counsellor, self.lead.pk, {"selected_university": self.university, "selected_course": self.course})
        University.objects.filter(pk=self.university.pk).update(is_active=False)
        self.university.refresh_from_db()
        with self.assertRaises(ValidationError):
            services.update_lead(self.counsellor, self.lead.pk, {"selected_university": self.university})

    def test_deactivation_retains_history_and_progression(self):
        services.update_lead(self.counsellor, self.lead.pk, {"selected_university": self.university, "selected_course": self.course})
        University.objects.filter(pk=self.university.pk).update(is_active=False)
        Course.objects.filter(pk=self.course.pk).update(is_active=False, intake_status="CLOSED")
        lead = services.change_status(self.counsellor, self.lead.pk, "CONTACTED")
        self.assertEqual(lead.selected_course_id, self.course.pk)
        form = LeadForm(instance=lead, actor=self.counsellor)
        self.assertTrue(form.fields["selected_course"].queryset.filter(pk=self.course.pk).exists())
        with self.assertRaises(ProtectedError):
            self.course.delete()
        with self.assertRaises(ProtectedError):
            self.university.delete()
        self.course.university = self.other_university
        with self.assertRaises(ValidationError):
            self.course.full_clean()

    def test_api_selection_uses_same_validation(self):
        api = APIClient()
        api.force_authenticate(self.counsellor)
        url = f"/api/v1/leads/{self.lead.pk}/"
        response = api.patch(url, {"selected_university": self.other_university.pk, "selected_course": self.course.pk}, format="json")
        self.assertEqual(response.status_code, 400)
        response = api.patch(url, {"selected_university": self.university.pk, "selected_course": self.course.pk}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["selected_course"], self.course.pk)

    def test_csrf_and_admin_management(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(reverse("courses:create"), self.course_data()).status_code, 403)
        self.assertEqual(client.post(reverse("universities:status", args=[self.university.pk]), {"action": "deactivate"}).status_code, 403)
        from django.contrib import admin
        from django.test import RequestFactory
        request = RequestFactory().get("/admin/")
        request.user = self.admin
        for model in (University, Course):
            registered = admin.site._registry[model]
            self.assertTrue(registered.has_change_permission(request))
            self.assertFalse(registered.has_delete_permission(request))
            request.user = self.counsellor
            self.assertFalse(registered.has_change_permission(request))
            request.user = self.admin

    def test_counsellor_saves_selection_from_existing_lead_form(self):
        self.client.force_login(self.counsellor)
        response = self.client.post(reverse("leads:edit", args=[self.lead.pk]), {
            "full_name": self.lead.full_name, "phone": self.lead.phone,
            "lead_source": "OTHER", "priority": "MEDIUM", "preferred_study_mode": "UNDECIDED",
            "desired_course": "Original preference", "selected_university": self.university.pk,
            "selected_course": self.course.pk,
        })
        self.assertRedirects(response, reverse("leads:detail", args=[self.lead.pk]))
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.selected_course_id, self.course.pk)
        self.assertEqual(self.lead.selected_university_id, self.university.pk)
