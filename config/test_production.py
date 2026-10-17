import json
import logging
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
from unittest.mock import patch
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from .logging import SafeJSONFormatter


class ProductionSettingsTests(SimpleTestCase):
    def environment(self, **changes):
        env = os.environ.copy()
        root = Path(tempfile.gettempdir()) / ("crm-production-check-" + secrets.token_hex(6))
        env.update(DJANGO_SETTINGS_MODULE="config.production", DEBUG="True",
            SECRET_KEY=secrets.token_urlsafe(64), DATABASE_URL="postgresql://check:check@127.0.0.1:5432/unused",
            ALLOWED_HOSTS="teachermitra.com,www.teachermitra.com",
            CSRF_TRUSTED_ORIGINS="https://teachermitra.com,https://www.teachermitra.com",
            CORS_ALLOWED_ORIGINS="", STATIC_ROOT=str(root / "static"), MEDIA_ROOT=str(root / "media"),
            PRIVATE_DOCUMENT_ROOT=str(root / "private"), CACHE_ROOT=str(root / "cache"))
        env.update(changes)
        return env

    def run_settings(self, env):
        # No DB connection, filesystem mutation, or output of secret settings.
        code = "import django; django.setup(); from django.conf import settings as s; import json; print(json.dumps({'debug':s.DEBUG,'secure':s.SESSION_COOKIE_SECURE,'proxy':s.SECURE_PROXY_SSL_HEADER,'hosts':s.ALLOWED_HOSTS,'hsts':s.SECURE_HSTS_SECONDS,'db':s.DATABASES['default']['ENGINE']}))"
        return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=30)

    def test_secure_defaults_override_inherited_development_debug(self):
        result = self.run_settings(self.environment())
        self.assertEqual(result.returncode, 0, "Production settings failed to load")
        value = json.loads(result.stdout)
        self.assertFalse(value["debug"])
        self.assertTrue(value["secure"])
        self.assertEqual(value["proxy"], ["HTTP_X_FORWARDED_PROTO", "https"])
        self.assertGreater(value["hsts"], 0)
        self.assertEqual(value["db"], "django.db.backends.postgresql")
        code = "import django; django.setup(); from django.core.checks import run_checks; import json; print(json.dumps([item.id for item in run_checks(include_deployment_checks=True)]))"
        check = subprocess.run([sys.executable, "-c", code], env=self.environment(), capture_output=True, text=True, timeout=30)
        self.assertEqual(check.returncode, 0)
        self.assertLessEqual(set(json.loads(check.stdout)), {"security.W005", "security.W021"})

    def test_missing_or_weak_secret_rejected(self):
        for secret in ("", "short", "x" * 70):
            with self.subTest(secret_length=len(secret)):
                self.assertNotEqual(self.run_settings(self.environment(SECRET_KEY=secret)).returncode, 0)

    def test_postgresql_required(self):
        self.assertNotEqual(self.run_settings(self.environment(DATABASE_URL="sqlite:///local.sqlite3")).returncode, 0)
        env = self.environment()
        env.pop("DATABASE_URL")
        self.assertNotEqual(self.run_settings(env).returncode, 0)

    def test_explicit_hosts_and_https_origins_required(self):
        for fields in ({"ALLOWED_HOSTS": "*"}, {"ALLOWED_HOSTS": ""},
            {"CSRF_TRUSTED_ORIGINS": "http://teachermitra.com"}, {"CORS_ALLOWED_ORIGINS": "https://*.example.com"}):
            self.assertNotEqual(self.run_settings(self.environment(**fields)).returncode, 0)

    def test_private_storage_cannot_be_public_or_inside_release(self):
        env = self.environment()
        env["PRIVATE_DOCUMENT_ROOT"] = env["MEDIA_ROOT"]
        self.assertNotEqual(self.run_settings(env).returncode, 0)
        self.assertNotEqual(self.run_settings(self.environment(PRIVATE_DOCUMENT_ROOT=str(Path(__file__).resolve().parent / "private"))).returncode, 0)

    def test_logging_does_not_interpolate_secrets_or_exception_details(self):
        try:
            raise RuntimeError("database-password-and-private-file")
        except RuntimeError:
            record = logging.LogRecord("django.request", logging.ERROR, __file__, 1,
                "token=%s /path?password=secret", ("secret-token",), sys.exc_info())
        record.status_code = 500
        value = SafeJSONFormatter().format(record)
        self.assertNotIn("secret", value)
        self.assertNotIn("database-password", value)
        self.assertEqual(json.loads(value)["exception_type"], "RuntimeError")


@override_settings(SECURE_SSL_REDIRECT=False)
class HealthTests(TestCase):
    def test_liveness_and_database_readiness(self):
        for name in ("health", "ready"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"status": "ok"})
            self.assertIn("no-store", response["Cache-Control"])
            self.assertEqual(self.client.post(reverse(name)).status_code, 405)

    def test_readiness_failure_is_generic(self):
        with patch("config.views.connections") as connections:
            connections.__getitem__.return_value.cursor.side_effect = RuntimeError("secret-db-details")
            response = self.client.get(reverse("ready"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})
        self.assertNotIn(b"secret", response.content)

    def test_secure_proxy_and_host_validation(self):
        with override_settings(SECURE_SSL_REDIRECT=True, SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"), ALLOWED_HOSTS=["teachermitra.com"]):
            self.assertEqual(self.client.get(reverse("health"), HTTP_HOST="teachermitra.com").status_code, 301)
            self.assertEqual(self.client.get(reverse("health"), HTTP_HOST="teachermitra.com", HTTP_X_FORWARDED_PROTO="https").status_code, 200)
            self.assertEqual(self.client.get(reverse("health"), HTTP_HOST="bad.example").status_code, 400)
