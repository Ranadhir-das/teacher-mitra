from django.urls import path

from . import views


app_name = "followups"


urlpatterns = [
    path(
        "",
        views.followup_list,
        name="list",
    ),
    path(
        "lead/<int:lead_id>/create/",
        views.followup_create,
        name="create",
    ),
    path(
        "<int:pk>/complete/",
        views.followup_complete,
        name="complete",
    ),
    path(
        "<int:pk>/cancel/",
        views.followup_cancel,
        name="cancel",
    ),
]