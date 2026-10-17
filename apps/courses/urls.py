from django.urls import path
from apps.universities import views

app_name = "courses"
urlpatterns = [
    path("", views.index, {"kind": "course"}, name="list"),
    path("create/", views.edit, {"kind": "course"}, name="create"),
    path("<int:pk>/", views.detail, {"kind": "course"}, name="detail"),
    path("<int:pk>/edit/", views.edit, {"kind": "course"}, name="edit"),
    path("<int:pk>/status/", views.status, {"kind": "course"}, name="status"),
]
