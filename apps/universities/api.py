"""Education master management and shared, read-only active choices."""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, viewsets, mixins
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission, SAFE_METHODS
from rest_framework.response import Response
from apps.accounts.permissions import can_manage_employees, is_internal_user
from apps.partners.permissions import current_partner
from apps.leads.api.serializers import StrictSerializerMixin
from .models import Country, University
from apps.courses.models import Course


class MasterPermission(BasePermission):
    def has_permission(self, request, view):
        return is_internal_user(request.user) if request.method in SAFE_METHODS else can_manage_employees(request.user)


class ChoicePermission(BasePermission):
    def has_permission(self, request, view):
        if is_internal_user(request.user):
            return True
        if request.user.is_authenticated and request.user.role == "PARTNER":
            current_partner(request.user)
            return True
        return False


class CheckedModelSerializer(StrictSerializerMixin, serializers.ModelSerializer):
    def validate(self, attrs):
        attrs = super().validate(attrs)
        instance = self.Meta.model.objects.get(pk=self.instance.pk) if self.instance else self.Meta.model()
        for key, value in attrs.items():
            setattr(instance, key, value)
        try:
            instance.full_clean()
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
        # Carry normalized values from model validation into the saved object.
        for key in attrs:
            attrs[key] = getattr(instance, key)
        return attrs


class CountrySerializer(CheckedModelSerializer):
    class Meta:
        model = Country
        fields = ("id", "name", "code", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")
        validators = []  # Model full_clean also enforces case-insensitive uniqueness.


class UniversitySerializer(CheckedModelSerializer):
    country_name = serializers.CharField(source="country.name", read_only=True)

    class Meta:
        model = University
        fields = ("id", "name", "country", "country_name", "website", "description", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")
        validators = []


class CourseSerializer(CheckedModelSerializer):
    university_name = serializers.CharField(source="university.name", read_only=True)
    country = serializers.IntegerField(source="university.country_id", read_only=True)
    country_name = serializers.CharField(source="university.country.name", read_only=True)

    class Meta:
        model = Course
        fields = ("id", "name", "university", "university_name", "country", "country_name", "program", "duration_months", "fees", "currency", "eligibility", "mode", "intake", "intake_status", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")
        validators = []


class MasterViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                    mixins.UpdateModelMixin, viewsets.GenericViewSet):
    permission_classes = [MasterPermission]
    filter_fields = ()
    search_fields = ("name",)

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action != "list":
            return qs
        search = self.request.query_params.get("search", "").strip()[:200]
        if search:
            query = Q()
            for field in self.search_fields:
                query |= Q(**{field + "__icontains": search})
            qs = qs.filter(query)
        for field in self.filter_fields:
            value = self.request.query_params.get(field)
            if value:
                if field in ("country", "university") and not value.isdecimal():
                    raise ValidationError({field: "Use a numeric ID."})
                lookup = "university__country" if field == "country" and self.queryset.model == Course else field
                qs = qs.filter(**{lookup: value})
        active = self.request.query_params.get("is_active")
        if active is not None:
            if active not in ("true", "false"):
                raise ValidationError({"is_active": "Use true or false."})
            qs = qs.filter(is_active=active == "true")
        return qs

    def perform_create(self, serializer):
        self.save_checked(serializer)

    def perform_update(self, serializer):
        self.save_checked(serializer)

    def save_checked(self, serializer):
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError:
            raise ValidationError({"detail": "A matching education entry already exists."})

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        return self.set_active(True)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        return self.set_active(False)

    def set_active(self, active):
        serializer = self.get_serializer(self.get_object(), data={"is_active": active}, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)


class CountryViewSet(MasterViewSet):
    queryset = Country.objects.all()
    serializer_class = CountrySerializer
    search_fields = ("name", "code")


class UniversityViewSet(MasterViewSet):
    queryset = University.objects.select_related("country").all()
    serializer_class = UniversitySerializer
    filter_fields = ("country",)
    search_fields = ("name", "country__name", "country__code")


class CourseViewSet(MasterViewSet):
    queryset = Course.objects.select_related("university__country").all()
    serializer_class = CourseSerializer
    filter_fields = ("country", "university", "mode", "intake_status")
    search_fields = ("name", "program", "university__name", "university__country__name")


class EducationChoices(mixins.ListModelMixin, viewsets.GenericViewSet):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [ChoicePermission]
    # Choices contain only active shared catalogue rows; partners have no writes.
    def get_serializer_class(self):
        return {"countries": CountrySerializer, "universities": UniversitySerializer, "courses": CourseSerializer}[self.kwargs["kind"]]

    def get_queryset(self):
        kind = self.kwargs["kind"]
        if kind == "countries":
            return Country.objects.filter(is_active=True)
        if kind == "universities":
            country = get_object_or_404(Country, pk=self.kwargs["pk"], is_active=True)
            return University.objects.filter(country=country, is_active=True).select_related("country")
        university = get_object_or_404(University.objects.select_related("country"), pk=self.kwargs["pk"], is_active=True, country__is_active=True)
        return Course.objects.filter(university=university, is_active=True, intake_status__in=["OPEN", "UPCOMING"]).select_related("university__country")
