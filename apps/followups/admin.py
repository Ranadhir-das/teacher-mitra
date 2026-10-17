from django.contrib import admin

from .models import FollowUp


@admin.register(FollowUp)
class FollowUpAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "lead",
        "followup_type",
        "scheduled_at",
        "assigned_to",
        "status",
        "completed_at",
        "created_at",
    )

    list_filter = (
        "status",
        "followup_type",
        "assigned_to",
        "scheduled_at",
    )

    search_fields = (
        "lead__full_name",
        "lead__phone",
        "lead__email",
        "assigned_to__username",
        "assigned_to__email",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "completed_at",
    )

    ordering = (
        "scheduled_at",
        "pk",
    )

    list_select_related = (
        "lead",
        "assigned_to",
        "created_by",
    )