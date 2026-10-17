from django.urls import path
from .api import EducationChoices

app_name = "education"
urlpatterns = [
    path("countries/", EducationChoices.as_view({"get": "list"}), {"kind": "countries"}, name="countries"),
    path("countries/<int:pk>/universities/", EducationChoices.as_view({"get": "list"}), {"kind": "universities"}, name="universities"),
    path("universities/<int:pk>/courses/", EducationChoices.as_view({"get": "list"}), {"kind": "courses"}, name="courses"),
]
