from django.urls import path
from apps.universities import views

app_name = "universities"
urlpatterns = [
    path("", views.index, {"kind": "university"}, name="list"),
    path("create/", views.edit, {"kind": "university"}, name="create"),
    path("<int:pk>/", views.detail, {"kind": "university"}, name="detail"),
    path("<int:pk>/edit/", views.edit, {"kind": "university"}, name="edit"),
    path("<int:pk>/status/", views.status, {"kind": "university"}, name="status"),
]
