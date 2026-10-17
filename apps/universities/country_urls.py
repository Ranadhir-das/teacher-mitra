from django.urls import path
from apps.universities import views

app_name = "countries"
urlpatterns = [
    path("", views.index, {"kind": "country"}, name="list"),
    path("create/", views.edit, {"kind": "country"}, name="create"),
    path("<int:pk>/", views.detail, {"kind": "country"}, name="detail"),
    path("<int:pk>/edit/", views.edit, {"kind": "country"}, name="edit"),
    path("<int:pk>/status/", views.status, {"kind": "country"}, name="status"),
]
