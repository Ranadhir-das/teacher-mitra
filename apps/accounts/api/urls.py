from django.urls import path
from .views import LoginView, LogoutView, MeView, RefreshView

app_name = "auth-api"
urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("refresh/", RefreshView.as_view(), name="refresh"),
]
