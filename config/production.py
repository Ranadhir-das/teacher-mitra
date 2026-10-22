"""Fail-closed settings for the reviewed Nginx/systemd production deployment."""
import os
from django.core.exceptions import ImproperlyConfigured

# Never accidentally import the development checkout's .env in production.
os.environ["DJANGO_READ_DOT_ENV"] = "False"
os.environ["DEBUG"] = "False"
from .settings import *  # noqa: F403,E402

DEBUG = False
if len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5 or SECRET_KEY.startswith("django-insecure-"):
    raise ImproperlyConfigured("Production requires an independently generated SECRET_KEY of at least 50 characters.")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["teachermitra.com", "www.teachermitra.com"])
if not ALLOWED_HOSTS or any("*" in host for host in ALLOWED_HOSTS):
    raise ImproperlyConfigured("Set explicit production ALLOWED_HOSTS; wildcards are forbidden.")
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=["https://teachermitra.com", "https://www.teachermitra.com"])
if not CSRF_TRUSTED_ORIGINS or any(not origin.startswith("https://") or "*" in origin for origin in CSRF_TRUSTED_ORIGINS):
    raise ImproperlyConfigured("Production CSRF origins must be explicit HTTPS origins.")
DATABASES = {"default": env.db("DATABASE_URL")}
if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise ImproperlyConfigured("Production requires a PostgreSQL DATABASE_URL.")
DATABASES["default"]["CONN_MAX_AGE"] = 60
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DATABASES["default"].setdefault("OPTIONS", {}).setdefault("connect_timeout", 5)

# Set only behind the supplied trusted proxy: upstream is loopback-only and
# Nginx replaces (never appends/trusts) the incoming forwarded headers.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = False
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=3600)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
if SECURE_HSTS_SECONDS < 0:
    raise ImproperlyConfigured("SECURE_HSTS_SECONDS cannot be negative.")

# All writable storage must be outside immutable release checkouts, and each
# directory must be independent so public aliases cannot expose private data.
STATIC_ROOT = Path(env("STATIC_ROOT"))
MEDIA_ROOT = Path(env("MEDIA_ROOT"))
PRIVATE_DOCUMENT_ROOT = Path(env("PRIVATE_DOCUMENT_ROOT"))
CACHE_ROOT = Path(env("CACHE_ROOT"))
roots = [STATIC_ROOT, MEDIA_ROOT, PRIVATE_DOCUMENT_ROOT, CACHE_ROOT]
if any(not root.is_absolute() or root.resolve().is_relative_to(BASE_DIR.resolve()) for root in roots):
    raise ImproperlyConfigured("Production storage paths must be absolute and outside the release directory.")
for index, root in enumerate(roots):
    if any(root.resolve().is_relative_to(other.resolve()) or other.resolve().is_relative_to(root.resolve()) for other in roots[index + 1:]):
        raise ImproperlyConfigured("Production storage paths cannot overlap.")
FILE_UPLOAD_PERMISSIONS = 0o640
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o750
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FILES = 5

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
if any(not origin.startswith("https://") or "*" in origin for origin in CORS_ALLOWED_ORIGINS):
    raise ImproperlyConfigured("Production CORS origins must be explicit HTTPS origins.")
CACHES = {"default": {"BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
    "LOCATION": str(CACHE_ROOT), "TIMEOUT": 300, "OPTIONS": {"MAX_ENTRIES": 10000}}}
REST_FRAMEWORK = {**REST_FRAMEWORK,
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle", "rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"auth": "10/min", "anon": "60/min", "user": "600/min"},
    "NUM_PROXIES": 1,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"]}
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
PASSWORD_RESET_TIMEOUT = 60 * 60

# No request bodies, credentials, query strings, or exception messages are sent
# to the journal. Alerting should consume ERROR records; SMTP is opt-in.
LOGGING = {"version": 1, "disable_existing_loggers": False,
    "formatters": {"json": {"()": "config.logging.SafeJSONFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.server": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.db.backends": {"handlers": ["console"], "level": "WARNING", "propagate": False}}}
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="TeacherMitra <noreply@teachermitra.com>")
SERVER_EMAIL = env("SERVER_EMAIL", default="errors@teachermitra.com")
