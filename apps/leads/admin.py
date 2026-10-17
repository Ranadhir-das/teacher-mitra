from django.contrib import admin
from .models import Lead, LeadAssignment, LeadStatusHistory, LeadNote, Tag


class AuditReadOnlyAdmin(admin.ModelAdmin):
    """CRM writes go through services; no direct admin mutation or permanent deletion."""
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields] + [field.name for field in self.model._meta.many_to_many]


@admin.register(Lead)
class LeadAdmin(AuditReadOnlyAdmin):
    list_display = ("full_name", "phone", "status", "priority", "assigned_counsellor", "assigned_team", "is_active", "created_at")
    search_fields = ("full_name", "phone", "alternate_phone", "email")
    list_filter = ("status", "priority", "lead_source", "is_active", "assigned_team")
    list_select_related = ("assigned_counsellor", "assigned_team")
    ordering = ("-created_at",)
    fieldsets = (
        ("Personal", {"fields": ("full_name", "phone", "alternate_phone", "email", "date_of_birth", "gender", "address", "city", "state", "pincode")}),
        ("Education", {"fields": ("highest_qualification", "institution_name", "passing_year", "percentage_or_cgpa", "specialization")}),
        ("Requirements", {"fields": ("selected_country", "selected_university", "selected_course", "desired_course", "desired_specialization", "preferred_university", "preferred_study_mode", "budget", "career_goal", "additional_requirements")}),
        ("CRM", {"fields": ("status", "priority", "lead_source", "assigned_counsellor", "assigned_team", "tags", "general_notes", "is_active")}),
        ("Audit", {"fields": ("created_by", "updated_by", "created_at", "updated_at", "last_contacted_at")}),
    )


@admin.register(LeadAssignment)
class AssignmentAdmin(AuditReadOnlyAdmin):
    list_display = ("lead", "previous_counsellor", "new_counsellor", "assigned_by", "assigned_at")
    list_filter = ("assigned_at", "new_team")
    search_fields = ("lead__full_name", "reason")
    list_select_related = True
    ordering = ("-assigned_at",)


@admin.register(LeadStatusHistory)
class StatusHistoryAdmin(AuditReadOnlyAdmin):
    list_display = ("lead", "previous_status", "new_status", "changed_by", "changed_at")
    list_filter = ("new_status", "changed_at")
    search_fields = ("lead__full_name", "note")
    list_select_related = True
    ordering = ("-changed_at",)


@admin.register(LeadNote)
class NoteAdmin(AuditReadOnlyAdmin):
    list_display = ("lead", "created_by", "created_at", "updated_at")
    search_fields = ("lead__full_name", "note")
    list_filter = ("created_at",)
    list_select_related = True
    ordering = ("-created_at",)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    ordering = ("name",)

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    has_add_permission = has_view_permission
    has_change_permission = has_view_permission
