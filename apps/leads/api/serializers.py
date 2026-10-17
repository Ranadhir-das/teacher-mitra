from collections.abc import Mapping
from rest_framework import serializers
from apps.accounts.models import User, Team
from ..models import Lead, LeadNote, LeadAssignment, LeadStatusHistory, Tag
from ..services import EDITABLE_FIELDS


class EmployeeSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "name")


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ("id", "name")


class LeadSerializer(serializers.ModelSerializer):
    partner = serializers.SerializerMethodField()

    def get_partner(self, obj):
        if obj.partner_id:
            return {"partner_code": obj.partner.partner_code, "business_name": obj.partner.business_name}
        return None
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    source_display = serializers.CharField(source="get_lead_source_display", read_only=True)
    assigned_counsellor = EmployeeSummarySerializer(read_only=True)
    team_name = serializers.CharField(source="assigned_team.name", read_only=True, default=None)
    tags = TagSerializer(many=True, read_only=True)

    class Meta:
        model = Lead
        fields = ("id", *EDITABLE_FIELDS, "status", "status_display", "priority_display", "source_display", "assigned_counsellor",
                  "assigned_team", "team_name", "tags", "created_at", "updated_at", "last_contacted_at", "is_active", "location_preference", "partner_submitted_notes")
        read_only_fields = fields


class StrictSerializerMixin:
    def to_internal_value(self, data):
        if not isinstance(data, Mapping):
            raise serializers.ValidationError({"detail": "Expected a JSON object."})
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: "Unsupported field; use a dedicated action if applicable." for key in unknown})
        return super().to_internal_value(data)


from apps.universities.selection_serializers import LeadEducationValidationMixin


class LeadWriteSerializer(LeadEducationValidationMixin, StrictSerializerMixin, serializers.ModelSerializer):
    tags = serializers.PrimaryKeyRelatedField(queryset=Tag.objects.all(), many=True, required=False)
    confirm_duplicate = serializers.BooleanField(required=False, default=False)

    class Meta:
        model = Lead
        fields = (*EDITABLE_FIELDS, "tags", "confirm_duplicate")


class LeadCreateSerializer(LeadWriteSerializer):
    assigned_counsellor = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(is_active=True, role=User.Role.COUNSELLOR), required=False, allow_null=True)
    assigned_team = serializers.PrimaryKeyRelatedField(queryset=Team.objects.filter(is_active=True), required=False, allow_null=True)

    class Meta(LeadWriteSerializer.Meta):
        fields = (*LeadWriteSerializer.Meta.fields, "assigned_counsellor", "assigned_team")


class AssignmentSerializer(StrictSerializerMixin, serializers.Serializer):
    assigned_counsellor = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(is_active=True, role=User.Role.COUNSELLOR), allow_null=True)
    assigned_team = serializers.PrimaryKeyRelatedField(queryset=Team.objects.filter(is_active=True), allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")


class StatusSerializer(StrictSerializerMixin, serializers.Serializer):
    status = serializers.ChoiceField(choices=Lead.Status.choices)
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")


class NoteWriteSerializer(StrictSerializerMixin, serializers.Serializer):
    note = serializers.CharField(max_length=10000)


class NoteSerializer(serializers.ModelSerializer):
    created_by = EmployeeSummarySerializer(read_only=True)

    class Meta:
        model = LeadNote
        fields = ("id", "note", "created_by", "created_at", "updated_at")


class AssignmentHistorySerializer(serializers.ModelSerializer):
    previous_counsellor = EmployeeSummarySerializer(read_only=True)
    new_counsellor = EmployeeSummarySerializer(read_only=True)
    assigned_by = EmployeeSummarySerializer(read_only=True)

    class Meta:
        model = LeadAssignment
        fields = ("id", "previous_counsellor", "new_counsellor", "previous_team", "new_team", "assigned_by", "assigned_at", "reason")


class StatusHistorySerializer(serializers.ModelSerializer):
    changed_by = EmployeeSummarySerializer(read_only=True)
    previous_status_display = serializers.CharField(source="get_previous_status_display", read_only=True)
    new_status_display = serializers.CharField(source="get_new_status_display", read_only=True)

    class Meta:
        model = LeadStatusHistory
        fields = ("id", "previous_status", "new_status", "previous_status_display", "new_status_display", "changed_by", "changed_at", "note")
