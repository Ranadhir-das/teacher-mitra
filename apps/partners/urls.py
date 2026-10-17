from django.urls import path
from . import views, onboarding_views as onboarding

app_name = "partners"
urlpatterns = [
    path("<int:pk>/delete/", views.delete, name="delete"),
    path("<int:pk>/onboarding/", onboarding.review, name="onboarding"),
    path("documents/<int:pk>/review/", onboarding.document_review, name="document-review"),
    path("documents/<int:pk>/file/", onboarding.document_file, name="document-file"),
    path("<int:pk>/approve/", views.review, {"decision": "approve"}, name="approve"),
    path("<int:pk>/reject/", views.review, {"decision": "reject"}, name="reject"),
    path("", views.index, name="list"),
    path("create/", views.edit, name="create"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/edit/", views.edit, name="edit"),
    path("<int:pk>/status/", views.action, {"action": "status"}, name="status"),
    path("<int:pk>/account/", views.action, {"action": "account"}, name="account"),
    path("<int:pk>/account-access/", views.action, {"action": "account-access"}, name="account-access"),
]
