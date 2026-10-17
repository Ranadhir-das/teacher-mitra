from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from apps.leads.views import lead_list
from .views import health, ready

handler403 = "config.views.access_denied"

urlpatterns = [
    path("health/", health, name="health"),
    path("health/ready/", ready, name="ready"),
    path("countries/", include("apps.universities.country_urls")),
    path("documents/", include("apps.documents.urls")),
    path("applications/", include("apps.applications.urls")),
    path("universities/", include("apps.universities.urls")),
    path("courses/", include("apps.courses.urls")),
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("api/v1/", include("config.api_urls")),
    path("leads/", include("apps.leads.urls")),
    path("partners/", include("apps.partners.urls")),
    path("partner/", include("apps.partners.portal_urls")),
    path("students/", lead_list, {"students": True}, name="students"),
    path("", include("apps.dashboard.urls")),
    path("followups/", include("apps.followups.urls")),
    path("reports/", include("apps.reports.urls")),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
