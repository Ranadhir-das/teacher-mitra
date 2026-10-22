from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()
PASSWORD = "Test-only-Cedar-97!"


@override_settings(SECURE_SSL_REDIRECT=False)
class AccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser("root@example.com", PASSWORD, name="Root")
        cls.admin = User.objects.create_user("admin@example.com", PASSWORD, name="Admin", role=User.Role.ADMIN)
        cls.leader = User.objects.create_user("leader@example.com", PASSWORD, name="Leader", role=User.Role.TEAM_LEADER)
        cls.worker = User.objects.create_user("worker@example.com", PASSWORD, name="Worker")

    def setUp(self):
        cache.clear()

    def test_user_password_and_normalization(self):
        user = User.objects.create_user("Mixed@EXAMPLE.COM", PASSWORD, name="Mixed")
        self.assertEqual(user.email, "mixed@example.com")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertNotEqual(user.password, PASSWORD)
        self.assertEqual(user.role, User.Role.COUNSELLOR)
        self.assertEqual(user.get_full_name(), "Mixed")
        with self.assertRaises(ValueError):
            User.objects.create_user("")

    def test_case_insensitive_email_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user("WORKER@example.com", PASSWORD)

    def test_superuser_flags(self):
        self.assertTrue(self.root.is_staff and self.root.is_superuser)
        self.assertEqual(self.root.role, User.Role.SUPER_ADMIN)
        for overrides in ({"is_staff": False}, {"is_superuser": False}, {"is_active": False}, {"role": "ADMIN"}):
            with self.assertRaises(ValueError):
                User.objects.create_superuser("invalid@example.com", PASSWORD, **overrides)

    def test_dashboard_requires_login(self):
        dashboard_url = reverse("dashboard:index")
        self.assertRedirects(self.client.get(dashboard_url), f"/accounts/login/?next={dashboard_url}")
        self.client.force_login(self.worker)
        response = self.client.get(dashboard_url)
        self.assertContains(response, "Welcome, Worker")
        self.assertContains(response, "Today's follow-ups")
        self.assertContains(response, "Pending applications")
        self.assertNotContains(response, "Active employees")

    def test_login_and_post_logout(self):
        response = self.client.post(reverse("accounts:login"), {"username": "WORKER@example.com", "password": PASSWORD})
        self.assertRedirects(response, reverse("dashboard:index"))
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("accounts:logout")), reverse("accounts:login"))
        self.assertEqual(self.client.get(reverse("dashboard:index")).status_code, 302)

    def test_invalid_and_inactive_web_login(self):
        self.assertContains(self.client.post(reverse("accounts:login"), {"username": self.worker.email, "password": "bad"}), "Please enter a correct")
        self.worker.is_active = False
        self.worker.save()
        self.assertFalse(self.client.login(email=self.worker.email, password=PASSWORD))

    def test_employee_permissions_all_roles(self):
        for user, expected in ((self.root, 200), (self.admin, 200), (self.leader, 200), (self.worker, 403)):
            self.client.force_login(user)
            for url in (reverse("accounts:employee-list"), reverse("accounts:employee-create"), reverse("accounts:employee-detail", args=[self.worker.pk])):
                expected_status = 404 if user == self.leader and url == reverse("accounts:employee-detail", args=[self.worker.pk]) else expected
                self.assertEqual(self.client.get(url).status_code, expected_status)

    def test_employee_create_edit_and_status(self):
        self.client.force_login(self.admin)
        payload = {"name": "New Counsellor", "email": "new@example.com", "phone": "9876543210", "username": "new.employee", "employee_id": "EMP-NEW", "role": "COUNSELLOR", "password1": PASSWORD, "password2": PASSWORD}
        self.assertEqual(self.client.post(reverse("accounts:employee-create"), payload).status_code, 302)
        employee = User.objects.get(email=payload["email"])
        self.assertTrue(employee.check_password(PASSWORD))
        self.assertFalse(employee.is_staff)
        payload.update(name="New Leader", role="TEAM_LEADER", is_superuser="on", is_staff="on")
        self.assertEqual(self.client.post(reverse("accounts:employee-edit", args=[employee.pk]), payload).status_code, 302)
        employee.refresh_from_db()
        self.assertEqual(employee.role, "TEAM_LEADER")
        self.assertFalse(employee.is_superuser or employee.is_staff)
        url = reverse("accounts:employee-status", args=[employee.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        for action, active in (("deactivate", False), ("activate", True)):
            self.assertEqual(self.client.post(url, {"action": action}).status_code, 302)
            employee.refresh_from_db()
            self.assertEqual(employee.is_active, active)

    def test_admin_cannot_elevate_or_modify_root(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("accounts:employee-edit", args=[self.root.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("accounts:employee-status", args=[self.root.pk]), {"action": "deactivate"}).status_code, 403)
        payload = {"name": "Bad", "email": "bad@example.com", "role": "SUPER_ADMIN", "password1": PASSWORD, "password2": PASSWORD}
        self.assertEqual(self.client.post(reverse("accounts:employee-create"), payload).status_code, 200)
        self.assertFalse(User.objects.filter(email="bad@example.com").exists())

    def test_self_protection(self):
        self.client.force_login(self.root)
        self.assertEqual(self.client.post(reverse("accounts:employee-status", args=[self.root.pk]), {"action": "deactivate"}).status_code, 403)
        self.client.post(reverse("accounts:employee-edit", args=[self.root.pk]), {"name": "Root", "email": self.root.email, "role": "COUNSELLOR"})
        self.root.refresh_from_db()
        self.assertEqual(self.root.role, "SUPER_ADMIN")

    def test_csrf_required_for_web_mutations(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(reverse("accounts:employee-status", args=[self.worker.pk]), {"action": "deactivate"}).status_code, 403)

    def test_deactivation_invalidates_session(self):
        self.client.force_login(self.worker)
        User.objects.filter(pk=self.worker.pk).update(is_active=False)
        self.assertEqual(self.client.get(reverse("dashboard:index")).status_code, 302)

    def test_admin_user_pages(self):
        self.client.force_login(self.root)
        for url in ("/admin/accounts/user/", "/admin/accounts/user/add/", f"/admin/accounts/user/{self.worker.pk}/change/"):
            self.assertEqual(self.client.get(url).status_code, 200)

    @override_settings(DEBUG=False, SECURE_SSL_REDIRECT=False)
    def test_custom_error_pages(self):
        self.assertContains(self.client.get("/not-a-page/"), "Page not found", status_code=404)
        self.client.force_login(self.worker)
        self.assertContains(self.client.get(reverse("accounts:employee-list")), "Access restricted", status_code=403)
        from django.template.loader import render_to_string
        self.assertIn("Something went wrong", render_to_string("500.html"))


@override_settings(SECURE_SSL_REDIRECT=False)
class APITests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("api@example.com", PASSWORD, name="API User")
        self.api = APIClient()

    def login(self):
        response = self.api.post("/api/v1/auth/login/", {"email": "API@example.com", "password": PASSWORD}, format="json")
        self.assertEqual(response.status_code, 200)
        self.api.credentials(HTTP_AUTHORIZATION="Bearer " + response.data["access"])
        return response.data

    def test_me_requires_jwt_and_returns_safe_fields(self):
        self.assertEqual(self.api.get("/api/v1/auth/me/").status_code, 401)
        self.login()
        response = self.api.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["email"], self.user.email)
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.last_login)
        self.assertNotIn("password", response.data)
        self.assertEqual(self.api.patch("/api/v1/auth/me/", {"role": "ADMIN"}).status_code, 405)

    def test_logout_revokes_refresh(self):
        tokens = self.login()
        self.assertEqual(self.api.post("/api/v1/auth/logout/", {"refresh": tokens["refresh"]}).status_code, 204)
        self.assertEqual(self.api.post("/api/v1/auth/refresh/", {"refresh": tokens["refresh"]}).status_code, 401)

    def test_rotation_blacklists_previous_refresh(self):
        tokens = self.login()
        response = self.api.post("/api/v1/auth/refresh/", {"refresh": tokens["refresh"]})
        self.assertEqual(response.status_code, 200)
        self.assertIn("refresh", response.data)
        self.assertEqual(self.api.post("/api/v1/auth/refresh/", {"refresh": tokens["refresh"]}).status_code, 401)

    def test_logout_rejects_other_users_token_and_invalid_tokens(self):
        other = User.objects.create_user("other@example.com", PASSWORD, name="Other")
        self.login()
        for payload in ({"refresh": str(RefreshToken.for_user(other))}, {"refresh": "invalid"}, {}):
            self.assertEqual(self.api.post("/api/v1/auth/logout/", payload).status_code, 400)

    def test_invalid_and_inactive_login(self):
        self.assertEqual(self.api.post("/api/v1/auth/login/", {"email": self.user.email, "password": "bad"}).status_code, 401)
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.api.post("/api/v1/auth/login/", {"email": self.user.email, "password": PASSWORD}).status_code, 401)

    def test_deactivation_denies_issued_access_and_refresh(self):
        tokens = self.login()
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.api.get("/api/v1/auth/me/").status_code, 401)
        self.assertEqual(self.api.post("/api/v1/auth/refresh/", {"refresh": tokens["refresh"]}).status_code, 401)

    def test_role_permission_uses_current_database_role(self):
        from apps.accounts.api.permissions import CanManageEmployees
        from rest_framework.test import APIRequestFactory
        request = APIRequestFactory().get("/")
        request.user = self.user
        self.assertFalse(CanManageEmployees().has_permission(request, None))
        self.user.role = "ADMIN"
        self.user.save()
        self.assertTrue(CanManageEmployees().has_permission(request, None))
