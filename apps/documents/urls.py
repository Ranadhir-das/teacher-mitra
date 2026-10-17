from django.urls import path
from . import views

app_name = "documents"
urlpatterns = [
    path("create/", views.document_create, name="create"),
    path("application/<int:application_id>/create/", views.document_create, name="application-create"),
    path("<int:pk>/", views.document_detail, name="detail"),
    path("<int:pk>/view/", views.document_file, name="view"),
    path("<int:pk>/download/", views.document_file, {"download": True}, name="download"),
]
