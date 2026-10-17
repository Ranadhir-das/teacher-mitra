from django.urls import path
from .views import MyProfileView, MyLeadsView, MyLeadDetailView

from . import onboarding

app_name = "partner-api"
urlpatterns = [
    path("onboarding/", onboarding.OnboardingView.as_view(), name="onboarding"),
    path("onboarding/submit/", onboarding.SubmitView.as_view(), name="onboarding-submit"),
    path("onboarding/documents/", onboarding.UploadView.as_view(), name="onboarding-upload"),
    path("onboarding/documents/<int:pk>/file/", onboarding.FileView.as_view(), name="onboarding-file"),
    path("", MyProfileView.as_view(), name="profile"),
    path("leads/", MyLeadsView.as_view(), name="leads"),
    path("leads/<int:pk>/", MyLeadDetailView.as_view(), name="detail"),
]
