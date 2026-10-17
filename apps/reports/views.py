from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.views.generic import TemplateView

from apps.accounts.models import User

from .services import (
    lead_report,
    counsellor_report,
    partner_report,
    application_report,
    admission_report,
)


class ReportsDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "reports/dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.role not in {
            User.Role.SUPER_ADMIN,
            User.Role.ADMIN,
            User.Role.TEAM_LEADER,
        }:
            raise PermissionDenied

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update(
            lead_report=lead_report(),
            counsellor_report=counsellor_report(),
            partner_report=partner_report(),
            application_report=application_report(),
            admission_report=admission_report(),
        )

        return context