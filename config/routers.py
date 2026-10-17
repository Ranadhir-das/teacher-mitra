from rest_framework.routers import DefaultRouter, APIRootView

from apps.leads.api.views import LeadViewSet, TagViewSet
from apps.leads.api.permissions import InternalUserPermission
from apps.partners.api.views import PartnerViewSet
from apps.followups.api.views import FollowUpViewSet


class InternalAPIRoot(APIRootView):
    permission_classes = [InternalUserPermission]


class CRMRouter(DefaultRouter):
    APIRootView = InternalAPIRoot


router = CRMRouter()

router.register("leads", LeadViewSet, basename="lead")
router.register("tags", TagViewSet, basename="tag")
router.register("partners", PartnerViewSet, basename="partner")
router.register("followups", FollowUpViewSet, basename="followup")
from apps.universities.api import CountryViewSet, UniversityViewSet, CourseViewSet
router.register("countries", CountryViewSet, basename="country")
router.register("universities", UniversityViewSet, basename="university")
router.register("courses", CourseViewSet, basename="course")
