from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from django.shortcuts import get_object_or_404
from ..models import Partner
from ..permissions import OnboardingPermission, ManagePartnersPermission
from .. import onboarding as service
from ..services import SIGNUP_FIELDS, register_partner
from .views import ServiceErrorsMixin
from apps.leads.api.serializers import StrictSerializerMixin
from ..forms import PartnerSignupForm
from ..onboarding_views import file_response


class DraftSerializer(StrictSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Partner
        fields = service.FIELDS


class DecisionSerializer(StrictSerializerMixin, serializers.Serializer):
    decision = serializers.ChoiceField(choices=["approve", "reject", "changes"])
    feedback = serializers.CharField(required=False, allow_blank=True, max_length=5000, default="")


class DocumentReviewSerializer(StrictSerializerMixin, serializers.Serializer):
    decision = serializers.ChoiceField(choices=["verify", "reject"])
    reason = serializers.CharField(required=False, allow_blank=True, max_length=5000, default="")


class UploadSerializer(StrictSerializerMixin, serializers.Serializer):
    document_type = serializers.ChoiceField(choices=service.DOCUMENT_TYPES)
    file = serializers.FileField()


def payload(partner, *, admin=False):
    progress = service.progress(partner)
    return {"partner_code": partner.partner_code, "status": partner.status, "status_display": partner.get_status_display(),
        "approved": partner.status == "ACTIVE", "profile": DraftSerializer(partner).data,
        "completion": progress["percent"], "complete": progress["complete"],
        "missing_fields": progress["missing_fields"], "missing_documents": progress["missing_documents"],
        "requirements": [{"code": item["code"], "label": item["label"]} for item in progress["requirements"]],
        "feedback": partner.review_feedback, "submitted_at": partner.submitted_at, "reviewed_at": partner.reviewed_at,
        "documents": [{"id": doc.pk, "document_type": doc.document_type, "status": doc.status,
            "original_name": doc.original_name, "rejection_reason": doc.rejection_reason,
            "download_url": (f"/api/v1/partners/onboarding-documents/{doc.pk}/" if admin else f"/api/v1/partners/my/onboarding/documents/{doc.pk}/file/")}
            for doc in partner.onboarding_documents.filter(deleted_at__isnull=True)]}


class OnboardingView(ServiceErrorsMixin, generics.GenericAPIView):
    permission_classes = [OnboardingPermission]
    serializer_class = DraftSerializer

    def get(self, request):
        return Response(payload(request.partner))

    def patch(self, request):
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(payload(service.save_draft(request.user, serializer.validated_data)))


class SubmitView(ServiceErrorsMixin, generics.GenericAPIView):
    permission_classes = [OnboardingPermission]

    def post(self, request):
        return Response(payload(service.submit_onboarding(request.user)))


class UploadView(ServiceErrorsMixin, generics.GenericAPIView):
    permission_classes = [OnboardingPermission]
    serializer_class = UploadSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doc = service.upload_document(request.user, serializer.validated_data["document_type"], serializer.validated_data["file"])
        return Response({"id": doc.pk, "status": doc.status}, status=201)


class FileView(ServiceErrorsMixin, generics.GenericAPIView):
    permission_classes = [OnboardingPermission]

    def get(self, request, pk):
        return file_response(service.accessible_document(request.user, pk))


class AdminReviewView(ServiceErrorsMixin, generics.GenericAPIView):
    permission_classes = [ManagePartnersPermission]
    serializer_class = DecisionSerializer

    def get(self, request, pk):
        return Response(payload(get_object_or_404(Partner, pk=pk), admin=True))

    def post(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(payload(service.review_onboarding(request.user, pk, **serializer.validated_data), admin=True))


class AdminDocumentView(ServiceErrorsMixin, generics.GenericAPIView):
    permission_classes = [ManagePartnersPermission]
    serializer_class = DocumentReviewSerializer

    def get(self, request, pk):
        return file_response(service.accessible_document(request.user, pk))

    def post(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doc = service.review_document(request.user, pk, **serializer.validated_data)
        return Response({"id": doc.pk, "status": doc.status})


class SignupView(ServiceErrorsMixin, generics.GenericAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        allowed = {*SIGNUP_FIELDS, "password", "password_confirm"}
        service.check_fields(request.data, allowed)
        form = PartnerSignupForm(request.data)
        if not form.is_valid():
            raise serializers.ValidationError(form.errors)
        partner = register_partner({field: form.cleaned_data[field] for field in SIGNUP_FIELDS}, form.cleaned_data["password"])
        return Response({"partner_code": partner.partner_code, "status": partner.status}, status=201)
