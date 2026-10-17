from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from apps.documents.services import lock_application
from apps.leads.models import Lead, LeadStatusHistory
from .models import Admission, AdmissionHistory
from .permissions import visible_applications
from .services import save_application

ADMISSION_FIELDS = ("enrollment_number", "admission_date", "status", "payment_status", "remarks")


def visible_admissions(actor):
    return Admission.objects.filter(application__in=visible_applications(actor))


def validate_admission(admission, old=None):
    if not admission.application.lead.is_active:
        raise ValidationError("Archived leads are read-only.")
    if admission.application.status not in ("SUBMITTED", "UNDER_REVIEW", "APPROVED") and not (old and old.status == admission.status == "CANCELLED"):
        raise ValidationError("Admissions require a submitted, under review or approved application.")
    if old and admission.status != old.status:
        allowed = {"PENDING": {"CONFIRMED", "CANCELLED"}, "CONFIRMED": {"CANCELLED"}, "CANCELLED": set()}
        if admission.status not in allowed[old.status]:
            raise ValidationError("This admission status transition is not permitted.")
    if not old and admission.status == "CANCELLED":
        raise ValidationError("Create a pending or confirmed admission first.")


@transaction.atomic
def save_admission(actor, application_id, data):
    if set(data) - set(ADMISSION_FIELDS):
        raise ValidationError("Unsupported admission fields.")
    application = lock_application(actor, application_id)
    old = Admission.objects.select_for_update().filter(application=application).first()
    admission = Admission.objects.get(pk=old.pk) if old else Admission(application=application, lead=application.lead,
        university=application.university, course=application.course, created_by=actor)
    before = {field: str(getattr(admission, field) or "") for field in ADMISSION_FIELDS} if old else {}
    for field, value in data.items():
        setattr(admission, field, value)
    admission.enrollment_number = admission.enrollment_number.strip()
    admission.updated_by = actor
    validate_admission(admission, old)
    confirming = admission.status == "CONFIRMED" and (not old or old.status != "CONFIRMED")
    if confirming:
        admission.confirmed_at = timezone.now()
        admission.confirmed_by = actor
    admission.full_clean()
    after = {field: str(getattr(admission, field) or "") for field in ADMISSION_FIELDS}
    changes = {key: {"before": before.get(key, ""), "after": value} for key, value in after.items() if before.get(key) != value}
    if changes or not old:
        admission.save()
        AdmissionHistory.objects.create(admission=admission, actor=actor, previous_status=old.status if old else "",
            new_status=admission.status, changes=changes)
    if confirming:
        if application.status != "APPROVED":
            save_application(actor, {"status": "APPROVED"}, pk=application.pk)
        lead = Lead.objects.select_for_update().get(pk=application.lead_id)
        if lead.status != Lead.Status.ADMISSION_CONFIRMED:
            previous = lead.status
            lead.status = Lead.Status.ADMISSION_CONFIRMED
            lead.updated_by = actor
            lead.save(update_fields=["status", "updated_by", "updated_at"])
            LeadStatusHistory.objects.create(lead=lead, previous_status=previous, new_status=lead.status,
                changed_by=actor, note=f"Admission #{admission.pk} confirmed for application #{application.pk}.")
    return admission
