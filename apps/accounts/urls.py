from django.contrib.auth.views import LogoutView
from django.urls import path
from . import views
from .counsellor_views import counsellor_password

app_name = "accounts"
urlpatterns = [
    path("employees/<int:pk>/delete/", views.EmployeeDeleteView.as_view(), name="employee-delete"),
    path("employees/<int:pk>/password/", counsellor_password, name="employee-password"),
    path("login/", views.WebLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("employees/", views.EmployeeListView.as_view(), name="employee-list"),
    path("employees/new/", views.EmployeeCreateView.as_view(), name="employee-create"),
    path("employees/<int:pk>/", views.EmployeeDetailView.as_view(), name="employee-detail"),
    path("employees/<int:pk>/edit/", views.EmployeeEditView.as_view(), name="employee-edit"),
    path("employees/<int:pk>/status/", views.EmployeeStatusView.as_view(), name="employee-status"),
]
