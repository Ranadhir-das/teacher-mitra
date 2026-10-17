from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from .permissions import LeadAccessPermission, InternalUserPermission
from .serializers import (LeadSerializer, LeadCreateSerializer, LeadWriteSerializer, AssignmentSerializer, StatusSerializer,
    NoteWriteSerializer, NoteSerializer, AssignmentHistorySerializer, StatusHistorySerializer, TagSerializer)
from .. import services
from ..filters import filter_leads
from ..models import Lead, Tag
from ..permissions import visible_leads, optimized


class LeadPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class LeadViewSet(viewsets.GenericViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    permission_classes = [LeadAccessPermission]
    serializer_class = LeadSerializer
    pagination_class = LeadPagination
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return optimized(visible_leads(self.request.user))

    def filter_queryset(self, queryset):
        if self.action not in ("list", "my"):
            return queryset
        queryset, form = filter_leads(queryset, self.request.query_params, self.request.user)
        if not form.is_valid():
            raise ValidationError(form.errors)
        return queryset

    def handle_exception(self, exc):
        if isinstance(exc, services.DuplicateLeadError):
            return Response({"code": "possible_duplicate", "detail": exc.messages[0], "matches": exc.matches,
                "confirmation_field": "confirm_duplicate"}, status=status.HTTP_409_CONFLICT)
        if isinstance(exc, DjangoValidationError):
            exc = ValidationError(exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages})
        elif isinstance(exc, Lead.DoesNotExist):
            exc = NotFound()
        return super().handle_exception(exc)

    def create(self, request):
        serializer = LeadCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        lead = services.create_lead(request.user, data_without_options(data), counsellor=data.get("assigned_counsellor"),
            team=data.get("assigned_team"), tags=data.get("tags", []), confirm_duplicate=data.get("confirm_duplicate", False))
        return Response(LeadSerializer(optimized(Lead.objects.filter(pk=lead.pk)).get()).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        lead = self.get_object()
        serializer = LeadWriteSerializer(instance=self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        result = services.update_lead(request.user, lead.pk, data_without_options(data), tags=data.get("tags"), confirm_duplicate=data.get("confirm_duplicate", False))
        return Response(LeadSerializer(optimized(Lead.objects.filter(pk=result.pk)).get()).data)

    def destroy(self, request, pk=None):
        services.archive_lead(request.user, self.get_object().pk)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"])
    def my(self, request):
        queryset = self.filter_queryset(self.get_queryset().filter(assigned_counsellor=request.user))
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(LeadSerializer(page, many=True).data)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        lead = self.get_object()
        serializer = AssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = services.assign_lead(request.user, lead.pk, data["assigned_counsellor"], data["assigned_team"], data["reason"])
        return Response(LeadSerializer(result).data)

    @action(detail=True, methods=["post"], url_path="status")
    def change_status(self, request, pk=None):
        lead = self.get_object()
        serializer = StatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = services.change_status(request.user, lead.pk, **serializer.validated_data)
        return Response(LeadSerializer(result).data)

    @action(detail=True, methods=["post", "get"])
    def notes(self, request, pk=None):
        lead = self.get_object()
        if request.method == "GET":
            page = self.paginate_queryset(lead.notes.select_related("created_by"))
            return self.get_paginated_response(NoteSerializer(page, many=True).data)
        serializer = NoteWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = services.add_note(request.user, lead.pk, serializer.validated_data["note"])
        return Response(NoteSerializer(note).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        lead = self.get_object()
        return Response({
            "assignments": AssignmentHistorySerializer(lead.assignment_history.select_related("previous_counsellor", "new_counsellor", "assigned_by"), many=True).data,
            "statuses": StatusHistorySerializer(lead.status_history.select_related("changed_by"), many=True).data,
        })

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        lead = services.archive_lead(request.user, self.get_object().pk, active=True)
        return Response(LeadSerializer(lead).data)


class TagViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [InternalUserPermission]
    queryset = Tag.objects.all()
    serializer_class = TagSerializer


def data_without_options(data):
    return {key: value for key, value in data.items() if key in services.EDITABLE_FIELDS}
