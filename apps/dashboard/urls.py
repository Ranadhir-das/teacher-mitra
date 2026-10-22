from django.urls import path
from .views import DashboardView

app_name = "dashboard"
urlpatterns = [path("workspace/", DashboardView.as_view(), name="index")]
