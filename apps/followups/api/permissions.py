from rest_framework.permissions import BasePermission

from apps.followups.permissions import FollowUpPermission


class FollowUpAPIPermission(FollowUpPermission):
    """API permission wrapper for existing FollowUp access rules."""

    pass
