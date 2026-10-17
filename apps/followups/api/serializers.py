from rest_framework import serializers

from apps.accounts.models import User
from apps.leads.models import Lead

from ..models import FollowUp
from ..permissions import assignee_choices


class FollowUpSerializer(serializers.ModelSerializer):
    lead_name = serializers.CharField(
        source="lead.full_name",
        read_only=True,
    )
    assigned_to_name = serializers.CharField(
        source="assigned_to.name",
        read_only=True,
    )
    created_by_name = serializers.CharField(
        source="created_by.name",
        read_only=True,
    )
    followup_type_display = serializers.CharField(
        source="get_followup_type_display",
        read_only=True,
    )
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    class Meta:
        model = FollowUp
        fields = (
            "id",
            "lead",
            "lead_name",
            "assigned_to",
            "assigned_to_name",
            "followup_type",
            "followup_type_display",
            "scheduled_at",
            "status",
            "status_display",
            "outcome",
            "notes",
            "completed_at",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "status",
            "status_display",
            "completed_at",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        )


class FollowUpCreateSerializer(serializers.Serializer):
    lead = serializers.PrimaryKeyRelatedField(
        queryset=Lead.objects.filter(is_active=True),
    )
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True),
    )
    followup_type = serializers.ChoiceField(
        choices=FollowUp.Type.choices,
        default=FollowUp.Type.CALL,
    )
    scheduled_at = serializers.DateTimeField()
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=10000,
    )

    def validate_assigned_to(self, value):
        request = self.context["request"]
        lead = self.initial_data.get("lead")

        if lead:
            try:
                lead_obj = Lead.objects.get(pk=lead, is_active=True)
            except Lead.DoesNotExist:
                raise serializers.ValidationError(
                    "Selected lead does not exist."
                )

            if not assignee_choices(
                request.user,
                lead_obj,
            ).filter(pk=value.pk).exists():
                raise serializers.ValidationError(
                    "Choose an accessible follow-up owner."
                )

        return value


class FollowUpUpdateSerializer(serializers.Serializer):
    scheduled_at = serializers.DateTimeField(required=False)
    followup_type = serializers.ChoiceField(
        choices=FollowUp.Type.choices,
        required=False,
    )
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=10000,
    )


class CompleteFollowUpSerializer(serializers.Serializer):
    outcome = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
    )
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=10000,
    )
