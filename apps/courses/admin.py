from django.contrib import admin
from apps.universities.admin import CatalogueAdmin
from .models import Course
from apps.universities.forms import CourseForm


@admin.register(Course)
class CourseAdmin(CatalogueAdmin):
    form = CourseForm
    list_display = ("name", "university", "country", "program", "mode", "intake", "intake_status", "fees", "currency", "is_active")
    list_filter = ("university__country", "university", "mode", "intake_status", "is_active")
    search_fields = ("name", "program", "university__name", "university__country__name", "intake")
    list_select_related = ("university__country",)

    @admin.display(ordering="university__country__name")
    def country(self, obj):
        return obj.university.country
