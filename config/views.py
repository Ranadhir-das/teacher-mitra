from django.shortcuts import render
from django.views.defaults import permission_denied
from django.http import JsonResponse
from django.db import connections
from django.views.decorators.http import require_safe
from django.views.decorators.cache import never_cache
import logging


def access_denied(request, exception):
    if request.user.is_authenticated and request.user.role == "PARTNER":
        return render(request, "partner_portal/denied.html", status=403)
    return permission_denied(request, exception)


@require_safe
@never_cache
def health(request):
    return JsonResponse({"status": "ok"})


@require_safe
@never_cache
def ready(request):
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        logging.getLogger(__name__).error("readiness_failed")
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
