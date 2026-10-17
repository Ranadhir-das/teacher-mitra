from django.urls import path
from . import views, onboarding_views as onboarding

app_name = "partner-portal"
urlpatterns = [
    path("onboarding/", onboarding.edit, name="onboarding"),
    path("onboarding/upload/", onboarding.upload, name="onboarding-upload"),
    path("onboarding/submit/", onboarding.submit, name="onboarding-submit"),
    path("onboarding/documents/<int:pk>/", onboarding.document_file, name="onboarding-file"),
    path("signup/", views.signup, name="signup"),
    path("reports/", views.portal_reports, name="reports"),
    path("", views.portal_dashboard, name="dashboard"),
    path("leads/", views.portal_list, name="leads"),
    path("leads/create/", views.portal_submit, name="submit"),
    path("leads/<int:pk>/", views.portal_detail, name="detail"),
    path("leads/<int:pk>/edit/", views.portal_submit, name="edit"),
    path("profile/", views.portal_profile, name="profile"),
]
