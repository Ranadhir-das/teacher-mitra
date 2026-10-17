from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from apps.applications.workflow_admin import WorkflowAdmin
from .models import Document, DocumentHistory
from .services import visible_documents


@admin.register(Document)
class DocumentAdmin(WorkflowAdmin):
    scope = staticmethod(visible_documents)
    create_url = "documents:create"
    exclude = ("file",)
    list_display = ("title", "application", "document_type", "status", "reviewed_by", "deleted_at", "manage_document")
    list_filter = ("document_type", "status", "deleted_at")
    search_fields = ("title", "lead__full_name", "application__reference", "original_name")
    list_select_related = ("application", "lead", "reviewed_by")

    def get_readonly_fields(self, request, obj=None):
        return super().get_readonly_fields(request, obj) + ["manage_document"]

    @admin.display(description="Document workflow")
    def manage_document(self, obj):
        return format_html('<a href="{}">View, download, upload, review or delete</a>', reverse("documents:detail", args=[obj.pk]))


@admin.register(DocumentHistory)
class DocumentHistoryAdmin(WorkflowAdmin):
    list_display = ("document", "action", "previous_status", "new_status", "actor", "created_at")

    @staticmethod
    def scope(actor):
        return DocumentHistory.objects.filter(document__in=visible_documents(actor))
