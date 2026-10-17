from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from apps.leads.api.views import LeadPagination
from apps.leads.api.serializers import LeadSerializer
from apps.leads.services import DuplicateLeadError
from apps.leads.permissions import optimized
from ..models import Partner
from ..permissions import ManagePartnersPermission, ActivePartnerPermission
from ..queries import partner_list, portal_leads
from .. import services
from .serializers import (PartnerSerializer, PartnerWriteSerializer, PartnerCreateSerializer, LoginAccountSerializer, AccountAccessSerializer,
    PublicProfileSerializer, ProfileWriteSerializer, PublicLeadSerializer, SubmissionSerializer)


class ServiceErrorsMixin:
    def handle_exception(self, exc):
        if isinstance(exc, DuplicateLeadError):
            return Response({"code": "possible_duplicate", "detail": exc.messages[0], "matches": exc.matches,
                "confirmation_field": "confirm_duplicate"}, status=409)
        if isinstance(exc, DjangoValidationError):
            exc = ValidationError(exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages})
        elif isinstance(exc, Partner.DoesNotExist):
            exc = NotFound()
        return super().handle_exception(exc)


class PartnerViewSet(ServiceErrorsMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [ManagePartnersPermission]
    serializer_class = PartnerSerializer
    pagination_class = LeadPagination
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return Partner.objects.select_related("user").annotate(total_leads=Count("leads"))

    def filter_queryset(self, queryset):
        if self.action != "list":
            return queryset
        queryset, form = partner_list(queryset, self.request.query_params)
        if not form.is_valid():
            raise ValidationError(form.errors)
        return queryset

    def create(self, request):
        serializer = PartnerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        create_login = data.pop("create_login", False)
        email, password = data.pop("login_email", ""), data.pop("password", "")
        partner = services.create_partner(request.user, data, create_login=create_login, login_email=email, password=password)
        return Response(PartnerSerializer(self.get_queryset().get(pk=partner.pk)).data, status=201)

    def partial_update(self, request, pk=None):
        partner = self.get_object()
        serializer = PartnerWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        services.update_partner(request.user, partner.pk, serializer.validated_data)
        return Response(PartnerSerializer(self.get_queryset().get(pk=partner.pk)).data)

    def destroy(self, request, pk=None):
        services.update_partner(request.user, self.get_object().pk, {"status": Partner.Status.INACTIVE})
        return Response(status=204)

    @action(detail=True, methods=["get"])
    def leads(self, request, pk=None):
        page = self.paginate_queryset(optimized(self.get_object().leads.all()))
        return self.get_paginated_response(LeadSerializer(page, many=True).data)

    @action(detail=True, methods=["post"])
    def account(self, request, pk=None):
        partner = self.get_object()
        serializer = LoginAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.create_login(request.user, partner.pk, serializer.validated_data["login_email"], serializer.validated_data["password"])
        return Response(PartnerSerializer(self.get_queryset().get(pk=partner.pk)).data, status=201)

    @action(detail=True, methods=["post"], url_path="account-access")
    def account_access(self, request, pk=None):
        partner = self.get_object()
        serializer = AccountAccessSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.account_access(request.user, partner.pk, serializer.validated_data["is_active"])
        return Response(PartnerSerializer(self.get_queryset().get(pk=partner.pk)).data)


class MyProfileView(ServiceErrorsMixin, generics.GenericAPIView):
    permission_classes = [ActivePartnerPermission]
    serializer_class = PublicProfileSerializer

    def get(self, request):
        return Response(PublicProfileSerializer(request.partner).data)

    def patch(self, request):
        serializer = ProfileWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        partner = services.update_profile(request.user, serializer.validated_data)
        return Response(PublicProfileSerializer(partner).data)


class MyLeadsView(ServiceErrorsMixin, generics.GenericAPIView):
    permission_classes = [ActivePartnerPermission]
    serializer_class = PublicLeadSerializer
    pagination_class = LeadPagination

    def get(self, request):
        # Reject ownership filters instead of letting them change the scoped queryset.
        if set(request.query_params) - {"search", "status", "sort", "page", "page_size"}:
            raise ValidationError("Unsupported partner lead filter.")
        queryset, form = portal_leads(request.partner.leads.all(), request.query_params)
        if not form.is_valid():
            raise ValidationError(form.errors)
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(PublicLeadSerializer(page, many=True).data)

    def post(self, request):
        serializer = SubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        confirm = data.pop("confirm_duplicate", False)
        lead = services.submit_lead(request.user, data, confirm_duplicate=confirm)
        return Response(PublicLeadSerializer(lead).data, status=201)


class MyLeadDetailView(ServiceErrorsMixin, generics.GenericAPIView):
    permission_classes = [ActivePartnerPermission]
    serializer_class = PublicLeadSerializer

    def get_object(self):
        from django.shortcuts import get_object_or_404
        return get_object_or_404(self.request.partner.leads.all(), pk=self.kwargs["pk"])

    def get(self, request, pk):
        return Response(PublicLeadSerializer(self.get_object()).data)

    def patch(self, request, pk):
        self.get_object()
        serializer = SubmissionSerializer(instance=self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        confirm = data.pop("confirm_duplicate", False)
        lead = services.edit_submission(request.user, pk, data, confirm_duplicate=confirm)
        return Response(PublicLeadSerializer(lead).data)
