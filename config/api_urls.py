from django.urls import include, path
from .routers import router
from apps.partners.api import onboarding

urlpatterns = [
    path("partners/signup/", onboarding.SignupView.as_view(), name="partner-signup-api"),
    path("partners/<int:pk>/onboarding/", onboarding.AdminReviewView.as_view(), name="partner-onboarding-review-api"),
    path("partners/onboarding-documents/<int:pk>/", onboarding.AdminDocumentView.as_view(), name="partner-document-review-api"),path("education/", include("apps.universities.education_urls")), path("auth/", include("apps.accounts.api.urls")),
    path("partners/my/", include("apps.partners.api.urls")), path("", include(router.urls))]
