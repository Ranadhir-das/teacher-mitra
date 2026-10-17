from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from django.utils import timezone

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.leads.permissions import visible_leads

from ..models import FollowUp
from ..permissions import visible_followups
from .. import services

from .permissions import FollowUpAPIPermission
from .serializers import (
    CompleteFollowUpSerializer,
    FollowUpCreateSerializer,
    FollowUpSerializer,
    FollowUpUpdateSerializer,
)


class FollowUpPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class FollowUpViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [FollowUpAPIPermission]
    pagination_class = FollowUpPagination
    serializer_class = FollowUpSerializer

    def get_queryset(self):
        return (
            visible_followups(self.request.user)
            .select_related(
                "lead",
                "assigned_to",
                "created_by",
            )
        )

    def handle_exception(self, exc):
        if isinstance(exc, DjangoValidationError):
            exc = ValidationError(
                exc.message_dict
                if hasattr(exc, "message_dict")
                else {"detail": exc.messages}
            )
        elif isinstance(exc, FollowUp.DoesNotExist):
            exc = NotFound()

        return super().handle_exception(exc)

    def create(self, request):
        serializer = FollowUpCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        followup = services.create_followup(
            lead=data["lead"],
            assigned_to=data["assigned_to"],
            created_by=request.user,
            followup_type=data["followup_type"],
            scheduled_at=data["scheduled_at"],
            notes=data.get("notes", ""),
        )

        return Response(
            FollowUpSerializer(followup).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, pk=None):
        followup = self.get_object()

        serializer = FollowUpUpdateSerializer(
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        if followup.status in {
            FollowUp.Status.COMPLETED,
            FollowUp.Status.CANCELLED,
        }:
            raise ValidationError(
                "Completed or cancelled follow-ups cannot be edited."
            )

        if "scheduled_at" in data:
            if data["scheduled_at"] < timezone.now():
                raise ValidationError(
                    "Follow-up time cannot be in the past."
                )
            followup.scheduled_at = data["scheduled_at"]

        if "followup_type" in data:
            followup.followup_type = data["followup_type"]

        if "notes" in data:
            followup.notes = data["notes"]

        followup.full_clean()
        followup.save()

        return Response(
            FollowUpSerializer(followup).data
        )

    def destroy(self, request, pk=None):
        followup = self.get_object()

        services.cancel_followup(
            followup=followup,
            actor=request.user,
        )

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"])
    def today(self, request):
        today = timezone.localdate()

        queryset = self.get_queryset().filter(
            scheduled_at__date=today,
        )

        page = self.paginate_queryset(queryset)

        return self.get_paginated_response(
            FollowUpSerializer(page, many=True).data
        )

    @action(detail=False, methods=["get"])
    def upcoming(self, request):
        queryset = self.get_queryset().filter(
            scheduled_at__gte=timezone.now(),
            status=FollowUp.Status.SCHEDULED,
        )

        page = self.paginate_queryset(queryset)

        return self.get_paginated_response(
            FollowUpSerializer(page, many=True).data
        )

    @action(detail=False, methods=["get"])
    def missed(self, request):
        queryset = self.get_queryset().filter(
            status=FollowUp.Status.MISSED,
        )

        page = self.paginate_queryset(queryset)

        return self.get_paginated_response(
            FollowUpSerializer(page, many=True).data
        )

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        followup = self.get_object()

        serializer = CompleteFollowUpSerializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)

        followup = services.complete_followup(
            followup=followup,
            actor=request.user,
            outcome=serializer.validated_data.get(
                "outcome",
                "",
            ),
            notes=serializer.validated_data.get(
                "notes",
                "",
            ),
        )

        return Response(
            FollowUpSerializer(followup).data
        )

    @action(detail=True, methods=["post"], url_path="mark-missed")
    def mark_missed(self, request, pk=None):
        followup = self.get_object()

        followup = services.mark_followup_missed(
            followup=followup,
            actor=request.user,
        )

        return Response(
            FollowUpSerializer(followup).data
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        followup = self.get_object()

        followup = services.cancel_followup(
            followup=followup,
            actor=request.user,
        )

        return Response(
            FollowUpSerializer(followup).data
        )
