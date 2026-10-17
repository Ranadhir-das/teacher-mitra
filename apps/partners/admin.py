from django.contrib import admin
from .models import Partner, PartnerOnboardingHistory
from django.urls import reverse
from django.utils.html import format_html
from .permissions import can_manage_partners


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ("partner_code", "business_name", "contact_person", "phone", "partner_type", "status", "created_at", "review_onboarding")
    list_filter = ("status", "partner_type")
    search_fields = ("partner_code", "business_name", "contact_person", "phone", "email")
    ordering = ("-created_at",)
    readonly_fields = ("partner_code", "user", "created_by", "created_at", "updated_at", "status", "review_onboarding")
    fieldsets = (
        ("Partner", {"fields": ("partner_code", "business_name", "contact_person", "partner_type", "status", "review_onboarding")}),
        ("Contact", {"fields": ("email", "phone", "alternate_phone", "address", "city", "state", "pincode")}),
        ("Internal", {"fields": ("notes", "user", "created_by", "created_at", "updated_at")}),
    )

    def get_readonly_fields(self, request, obj=None):
        fields = list(self.readonly_fields)
        if obj and obj.status == "SUBMITTED":
            from .services import PARTNER_FIELDS
            fields.extend(field for field in PARTNER_FIELDS if field != "notes")
        return tuple(dict.fromkeys(fields))

    def has_module_permission(self, request):
        return can_manage_partners(request.user)

    def has_view_permission(self, request, obj=None):
        return can_manage_partners(request.user)

    has_add_permission = has_view_permission
    has_change_permission = has_view_permission

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Onboarding")
    def review_onboarding(self, obj):
        if not obj or not obj.pk:
            return "Save the partner first."
        return format_html('<a href="{}">Review profile and documents</a>', reverse("partners:onboarding", args=[obj.pk]))

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
            obj.status = "REGISTERED"
        obj.full_clean()
        if change:
            from .services import update_partner, PARTNER_FIELDS
            update_partner(request.user, obj.pk, {field: getattr(obj, field) for field in form.changed_data if field in PARTNER_FIELDS})
        else:
            obj.save()
