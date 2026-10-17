from rest_framework import serializers
from apps.leads.models import Lead
from apps.leads.api.serializers import StrictSerializerMixin
from ..models import Partner
from ..services import PARTNER_FIELDS, PROFILE_FIELDS, SUBMISSION_FIELDS
from ..statuses import public_status


class PartnerSerializer(serializers.ModelSerializer):
    total_leads = serializers.IntegerField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    type_display = serializers.CharField(source="get_partner_type_display", read_only=True)
    login_email = serializers.EmailField(source="user.email", read_only=True, default=None)
    account_active = serializers.BooleanField(source="user.is_active", read_only=True, default=None)

    class Meta:
        model = Partner
        fields = ("id", "partner_code", *PARTNER_FIELDS, "status_display", "type_display", "total_leads", "login_email", "account_active", "created_at", "updated_at")
        read_only_fields = fields


class PartnerWriteSerializer(StrictSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Partner
        fields = PARTNER_FIELDS


class PartnerCreateSerializer(PartnerWriteSerializer):
    create_login = serializers.BooleanField(default=False)
    login_email = serializers.EmailField(required=False, allow_blank=True, write_only=True)
    password = serializers.CharField(required=False, write_only=True, trim_whitespace=False, style={"input_type": "password"})

    class Meta(PartnerWriteSerializer.Meta):
        fields = (*PARTNER_FIELDS, "partner_code", "create_login", "login_email", "password")
        extra_kwargs = {"partner_code": {"required": False}}


class LoginAccountSerializer(StrictSerializerMixin, serializers.Serializer):
    login_email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False, style={"input_type": "password"})


class AccountAccessSerializer(StrictSerializerMixin, serializers.Serializer):
    is_active = serializers.BooleanField()


class PublicProfileSerializer(serializers.ModelSerializer):
    partner_type_display = serializers.CharField(source="get_partner_type_display", read_only=True)

    class Meta:
        model = Partner
        fields = ("partner_code", *PROFILE_FIELDS, "partner_type_display")
        read_only_fields = fields


class ProfileWriteSerializer(StrictSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Partner
        fields = PROFILE_FIELDS


class PublicLeadSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)

    def get_status(self, obj):
        return public_status(obj)["code"]

    def get_status_display(self, obj):
        return public_status(obj)["label"]

    class Meta:
        model = Lead
        # Deliberate allowlist, independent of the internal LeadSerializer.
        fields = ("id", *SUBMISSION_FIELDS, "status", "status_display", "priority", "priority_display", "created_at", "updated_at")
        read_only_fields = fields


from apps.universities.selection_serializers import LeadEducationValidationMixin


class SubmissionSerializer(LeadEducationValidationMixin, StrictSerializerMixin, serializers.ModelSerializer):
    confirm_duplicate = serializers.BooleanField(required=False, default=False)

    class Meta:
        model = Lead
        fields = (*SUBMISSION_FIELDS, "confirm_duplicate")
