from django.urls import path

from .views import LeadCSVExportView, ReportsDashboardView


app_name = "reports"

urlpatterns = [
    path("leads.csv", LeadCSVExportView.as_view(), name="leads-csv"),
    path("", ReportsDashboardView.as_view(), name="dashboard"),
]
