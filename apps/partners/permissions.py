from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from functools import wraps
from rest_framework.permissions import BasePermission
from apps.accounts.permissions import can_manage_employees
from .models import Partner


def can_manage_partners(user):
    return can_manage_employees(user)


def current_partner(user, *, for_update=False):
    if not user.is_authenticated or not user.is_active or user.role != "PARTNER":
        raise PermissionDenied("A partner account is required.")
    queryset = Partner.objects.select_for_update() if for_update else Partner.objects.all()
    partner = queryset.filter(user_id=user.pk, status=Partner.Status.ACTIVE).first()
    if not partner:
        raise PermissionDenied("Your partner account is not active. Contact Aspiring Life Partners.")
    return partner


def partner_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        request.partner = current_partner(request.user)
        return view(request, *args, **kwargs)
    return wrapped


def manager_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not can_manage_partners(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped


class ManagePartnersPermission(BasePermission):
    def has_permission(self, request, view):
        return can_manage_partners(request.user)


class ActivePartnerPermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        request.partner = current_partner(request.user)
        return True


LOGIN_STATUSES = ("ACTIVE", "REGISTERED", "ONBOARDING", "SUBMITTED", "CHANGES_REQUIRED", "REJECTED")


def onboarding_partner(user, *, for_update=False):
    if not user.is_authenticated or not user.is_active or user.role != "PARTNER":
        raise PermissionDenied("A partner account is required.")
    qs = Partner.objects.select_for_update() if for_update else Partner.objects.all()
    partner = qs.filter(user_id=user.pk, status__in=LOGIN_STATUSES).first()
    if not partner:
        raise PermissionDenied("Your partner account is unavailable.")
    return partner


def onboarding_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        request.partner = onboarding_partner(request.user)
        return view(request, *args, **kwargs)
    return wrapped


class OnboardingPermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        request.partner = onboarding_partner(request.user)
        return True
