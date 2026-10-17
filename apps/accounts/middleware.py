from django.core.exceptions import PermissionDenied


class PartnerBoundaryMiddleware:
    """Session boundary; JWT views also enforce their own role permissions."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and user.role == "PARTNER":
            path = request.path_info
            allowed = (path in ("/health/", "/health/ready/") or path.startswith("/partner/") or path.startswith("/static/") or
                       path in ("/accounts/login/", "/accounts/logout/") or
                       path.startswith("/api/v1/education/") or path.startswith("/api/v1/auth/") or path.startswith("/api/v1/partners/my/"))
            if not allowed:
                raise PermissionDenied("Use the partner portal to access your referrals.")
        return self.get_response(request)
