from django.urls import path
from . import views
from .admission_views import admission_edit

app_name = "applications"
urlpatterns = [
    path("admissions/create/", admission_edit, name="admission-create"),
    path("<int:application_id>/admission/", admission_edit, name="admission-edit"),
    path("", views.application_list, name="list"),
    path("create/", views.application_edit, name="create"),
    path("<int:pk>/", views.application_detail, name="detail"),
    path("<int:pk>/edit/", views.application_edit, name="edit"),
]
