from io import BytesIO
import shutil
import uuid
from pathlib import Path
from django.conf import settings
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from apps.accounts.models import User
from apps.leads.models import Lead
from apps.courses.models import Course
from apps.universities.models import Country, University
from apps.applications.services import save_application


def image_upload(name="photo.png"):
    buffer = BytesIO()
    Image.new("RGB", (8, 8), "blue").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@override_settings(SECURE_SSL_REDIRECT=False)
class WorkflowTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("enrollment-admin@example.com", name="Admin", role="ADMIN", is_staff=True)
        cls.counsellor = User.objects.create_user("enrollment-counsellor@example.com", name="Counsellor", is_staff=True)
        cls.other = User.objects.create_user("enrollment-other@example.com", name="Other", is_staff=True)
        cls.leader = User.objects.create_user("enrollment-leader@example.com", name="Leader", role="TEAM_LEADER", is_staff=True)
        cls.partner = User.objects.create_user("enrollment-partner@example.com", name="Partner", role="PARTNER")
        cls.university = University.objects.create(country=Country.objects.get_or_create(name="Test Country")[0], name="Enrollment University")
        cls.course = Course.objects.create(university=cls.university, name="MBA", program="MBA", duration_months=24,
            fees=1000, eligibility="Graduate", mode="ONLINE", intake="2027")
        cls.lead = Lead.objects.create(full_name="Confidential student", phone="9876543210", created_by=cls.admin,
            updated_by=cls.admin, assigned_counsellor=cls.counsellor)
        cls.application = save_application(cls.counsellor, {"university": cls.university, "course": cls.course, "status": "STARTED"}, lead_id=cls.lead.pk)
        cls.application = save_application(cls.counsellor, {"status": "SUBMITTED"}, pk=cls.application.pk)

    def setUp(self):
        super().setUp()
        test_root = (Path(settings.BASE_DIR) / ".test_documents").resolve()
        test_root.mkdir(exist_ok=True)
        directory = (test_root / uuid.uuid4().hex).resolve()
        assert directory.is_relative_to(test_root)
        directory.mkdir()
        self.addCleanup(shutil.rmtree, directory)
        setting = override_settings(PRIVATE_DOCUMENT_ROOT=directory)
        setting.enable()
        self.addCleanup(setting.disable)
