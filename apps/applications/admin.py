from django.contrib import admin
from apps.accounts.permissions import is_internal_user
from .forms import ApplicationForm
from .models import Application, ApplicationStatusHistory
from .permissions import visible_applications
from .services import EDITABLE_FIELDS, save_application
from django.urls import reverse
from django.utils.html import format_html
from .models import Admission, AdmissionHistory
from .admissions import visible_admissions
from .workflow_admin import WorkflowAdmin


class HistoryInline(admin.TabularInline):
    model = ApplicationStatusHistory
    extra = 0
    fields = ("previous_status", "new_status", "changed_by", "changed_at", "changes")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return is_internal_user(request.user)


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    form = ApplicationForm
    fields = ("lead", "country") + EDITABLE_FIELDS + ("created_by", "updated_by", "created_at", "updated_at")
    readonly_fields = ("created_by", "updated_by", "created_at", "updated_at")
    list_display = ("id", "reference", "lead", "university", "course", "status", "submission_date")
    list_filter = ("status", "university", "submission_date")
    search_fields = ("reference", "lead__full_name", "course__name")
    list_select_related = ("lead", "university", "course")
    inlines = (HistoryInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(pk__in=visible_applications(request.user).values("pk"))

    def has_module_permission(self, request):
        return is_internal_user(request.user)

    def has_view_permission(self, request, obj=None):
        return is_internal_user(request.user) and (obj is None or visible_applications(request.user).filter(pk=obj.pk).exists())

    def has_add_permission(self, request):
        return is_internal_user(request.user)

    def has_change_permission(self, request, obj=None):
        return self.has_view_permission(request, obj) and (obj is None or obj.lead.is_active)

    def has_delete_permission(self, request, obj=None):
        return False

    def get_form(self, request, obj=None, **kwargs):
        base = super().get_form(request, obj, **kwargs)

        class ActorForm(base):
            def __init__(self, *args, **form_kwargs):
                super().__init__(*args, actor=request.user, **form_kwargs)

        return ActorForm

    def save_model(self, request, obj, form, change):
        saved = save_application(request.user, {field: form.cleaned_data[field] for field in EDITABLE_FIELDS},
            lead_id=obj.lead_id, pk=obj.pk if change else None)
        obj.__dict__.update(saved.__dict__)


@admin.register(ApplicationStatusHistory)
class ApplicationHistoryAdmin(admin.ModelAdmin):
    list_display = ("application", "previous_status", "new_status", "changed_by", "changed_at")
    readonly_fields = ("application", "previous_status", "new_status", "changed_by", "changed_at", "changes")

    def get_queryset(self, request):
        return super().get_queryset(request).filter(application__in=visible_applications(request.user)).select_related("application", "changed_by")

    def has_module_permission(self, request):
        return is_internal_user(request.user)

    def has_view_permission(self, request, obj=None):
        return is_internal_user(request.user) and (obj is None or visible_applications(request.user).filter(pk=obj.application_id).exists())

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Admission)
class AdmissionAdmin(WorkflowAdmin):
    scope = staticmethod(visible_admissions)
    create_url = "applications:admission-create"
    list_display = ("enrollment_number", "application", "lead", "status", "payment_status", "admission_date", "manage_admission")
    list_filter = ("status", "payment_status", "university")
    search_fields = ("enrollment_number", "lead__full_name", "application__reference")
    list_select_related = ("application", "lead", "university", "course")

    def get_readonly_fields(self, request, obj=None):
        return super().get_readonly_fields(request, obj) + ["manage_admission"]

    @admin.display(description="Admission workflow")
    def manage_admission(self, obj):
        return format_html('<a href="{}">Manage admission / enrollment</a>', reverse("applications:admission-edit", args=[obj.application_id]))


@admin.register(AdmissionHistory)
class AdmissionHistoryAdmin(WorkflowAdmin):
    list_display = ("admission", "previous_status", "new_status", "actor", "created_at")

    @staticmethod
    def scope(actor):
        return AdmissionHistory.objects.filter(admission__in=visible_admissions(actor))
