from django.urls import path
from . import views

app_name = "leads"
urlpatterns = [
    path("", views.lead_list, name="list"),
    path("new/", views.lead_edit, name="create"),
    path("bulk/", views.bulk_action, name="bulk"),
    path("tags/", views.tag_manage, name="tags"),
    path("tags/<int:pk>/", views.tag_manage, name="tag-edit"),
    path("<int:pk>/", views.lead_detail, name="detail"),
    path("<int:pk>/edit/", views.lead_edit, name="edit"),
    path("<int:pk>/<str:action>/", views.lead_action, name="action"),
]
