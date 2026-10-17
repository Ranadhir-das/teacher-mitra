"""Partner writes: explicit role checks, field allowlists and shared Lead validation."""
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404
from apps.accounts.models import User
from apps.leads.models import Lead, LeadStatusHistory
from apps.leads.services import duplicates, DuplicateLeadError
from .models import Partner, PartnerOnboardingHistory, generate_partner_code
from .permissions import can_manage_partners, current_partner
from .statuses import public_status

PARTNER_FIELDS = ("business_name", "contact_person", "email", "phone", "alternate_phone", "partner_type", "address", "city", "state", "pincode", "status", "notes")
PROFILE_FIELDS = ("business_name", "contact_person", "email", "phone", "alternate_phone", "address", "city", "state", "pincode")
SUBMISSION_FIELDS = ("full_name", "phone", "alternate_phone", "email", "date_of_birth", "gender", "highest_qualification", "passing_year",
    "percentage_or_cgpa", "specialization", "desired_course", "preferred_university", "preferred_study_mode", "location_preference", "partner_submitted_notes", "selected_country", "selected_university", "selected_course")


def require_manager(actor):
    if not can_manage_partners(actor):
        raise PermissionDenied


def check_fields(data, allowed):
    unknown = set(data) - set(allowed)
    if unknown:
        raise ValidationError({key: "This field cannot be modified here." for key in unknown})


def _create_login(partner, email, password):
    if partner.user_id:
        raise ValidationError("This partner already has a login account.")
    if not email or not password:
        raise ValidationError("Login email and password are required.")
    user = User(email=email.strip().lower(), name=partner.contact_person, phone=partner.phone, role=User.Role.PARTNER, is_active=partner.status in ("ACTIVE", "REGISTERED", "ONBOARDING", "SUBMITTED", "CHANGES_REQUIRED", "REJECTED"))
    user.full_clean(exclude=["password"])
    validate_password(password, user)
    user.set_password(password)
    try:
        with transaction.atomic():
            user.save()
    except IntegrityError:
        raise ValidationError({"login_email": "This login email is already in use."})
    partner.user = user
    partner.full_clean()
    partner.save()
    return user


@transaction.atomic
def create_partner(actor, data, *, create_login=False, login_email="", password=""):
    require_manager(actor)
    check_fields(data, (*PARTNER_FIELDS, "partner_code"))
    if data.get("status", "REGISTERED") not in ("PENDING", "REGISTERED"):
        raise ValidationError("New partners must complete onboarding before approval.")
    data = {**data, "status": "REGISTERED"}
    partner = Partner(**data, created_by=actor)
    generated = not data.get("partner_code")
    for attempt in range(5):
        if generated:
            partner.partner_code = generate_partner_code()
        partner.full_clean()
        try:
            with transaction.atomic():
                partner.save(force_insert=True)
            break
        except IntegrityError:
            if not generated or not Partner.objects.filter(partner_code=partner.partner_code).exists():
                raise
    else:
        raise ValidationError("Could not allocate a unique partner code. Please retry.")
    if create_login:
        _create_login(partner, login_email or partner.email, password)
    return partner


@transaction.atomic
def update_partner(actor, pk, data):
    require_manager(actor)
    check_fields(data, PARTNER_FIELDS)
    partner = Partner.objects.select_for_update().get(pk=pk)
    previous_status = partner.status
    restoring = (previous_status in ("SUSPENDED", "INACTIVE") and data.get("status") == "ACTIVE"
        and partner.onboarding_history.filter(previous_status="ACTIVE", action="STATUS_CHANGED").exists())
    if "status" in data and data["status"] != previous_status and data["status"] not in ("SUSPENDED", "INACTIVE") and not restoring:
        raise ValidationError("Use the onboarding review workflow to grant or restore approval.")
    if previous_status == "SUBMITTED" and set(data) - {"status", "notes"}:
        raise ValidationError("Request changes before editing a submitted registration.")
    for field, value in data.items():
        setattr(partner, field, value)
    partner.full_clean()
    partner.save()
    if partner.status != previous_status:
        PartnerOnboardingHistory.objects.create(partner=partner, actor=actor, action="STATUS_CHANGED", previous_status=previous_status, new_status=partner.status)
    if partner.status != previous_status and partner.user_id:
        active = partner.status == Partner.Status.ACTIVE
        User.objects.filter(pk=partner.user_id).update(is_active=active, account_status=User.Status.ACTIVE if active else User.Status.INACTIVE)
    return partner


@transaction.atomic
def create_login(actor, pk, email, password):
    require_manager(actor)
    partner = Partner.objects.select_for_update().get(pk=pk)
    return _create_login(partner, email, password)


@transaction.atomic
def account_access(actor, pk, active):
    require_manager(actor)
    partner = Partner.objects.select_for_update().select_related("user").get(pk=pk)
    if not partner.user_id:
        raise ValidationError("Create a login account first.")
    from .permissions import LOGIN_STATUSES
    if active and partner.status not in LOGIN_STATUSES:
        raise ValidationError("This partner status does not permit login.")
    partner.user.is_active = active
    partner.user.save(update_fields=["is_active"])
    return partner


@transaction.atomic
def update_profile(actor, data):
    partner = current_partner(actor, for_update=True)
    check_fields(data, PROFILE_FIELDS)
    for field, value in data.items():
        setattr(partner, field, value)
    partner.full_clean()
    partner.save()
    # Contact email is separate from login identity; no implicit credential change.
    return partner


def own_leads(actor):
    return Lead.objects.filter(partner=current_partner(actor))


def safe_duplicates(partner, matches):
    result = []
    for lead in matches.filter(partner=partner)[:10]:
        result.append({"id": lead.pk, "full_name": lead.full_name, "phone": lead.phone, "status": public_status(lead)["label"]})
    return result


@transaction.atomic
def submit_lead(actor, data, *, confirm_duplicate=False):
    partner = current_partner(actor, for_update=True)
    check_fields(data, SUBMISSION_FIELDS)
    lead = Lead(**data, partner=partner, lead_source=Lead.Source.PARTNER, created_by=actor, updated_by=actor)
    lead.full_clean()
    matches = duplicates(lead)
    if matches.exists() and not confirm_duplicate:
        raise DuplicateLeadError(safe_duplicates(partner, matches))
    lead.save()
    LeadStatusHistory.objects.create(lead=lead, previous_status="", new_status=Lead.Status.NEW, changed_by=actor, note="Partner submission.")
    return lead


def can_edit_submission(actor, lead):
    return lead.is_active and lead.status == Lead.Status.NEW and lead.created_by_id == actor.pk


@transaction.atomic
def edit_submission(actor, pk, data, *, confirm_duplicate=False):
    partner = current_partner(actor, for_update=True)
    lead = Lead.objects.select_for_update().filter(partner=partner, pk=pk).first()
    if not lead:
        raise Http404
    if not can_edit_submission(actor, lead):
        raise PermissionDenied("This submission is already being processed. Contact us to request a correction.")
    check_fields(data, SUBMISSION_FIELDS)
    if "selected_university" in data and "selected_country" not in data:
        data = {**data, "selected_country": data["selected_university"].country if data["selected_university"] else None}
    previous = (lead.phone, lead.alternate_phone, lead.email)
    for field, value in data.items():
        setattr(lead, field, value)
    lead.full_clean()
    matches = duplicates(lead)
    if previous != (lead.phone, lead.alternate_phone, lead.email) and matches.exists() and not confirm_duplicate:
        raise DuplicateLeadError(safe_duplicates(partner, matches))
    lead.updated_by = actor
    lead.save()
    return lead


SIGNUP_FIELDS = ("business_name", "contact_person", "email", "phone", "partner_type", "city", "state")


@transaction.atomic
def register_partner(data, password):
    """Public registration creates a login with onboarding-only permissions."""
    check_fields(data, SIGNUP_FIELDS)
    user = User(email=data["email"].strip().lower(), name=data["contact_person"],
                phone=data["phone"], role=User.Role.PARTNER, is_active=True)
    user.full_clean(exclude=["password"])
    validate_password(password, user)
    user.set_password(password)
    try:
        with transaction.atomic():
            user.save()
    except IntegrityError:
        raise ValidationError({"email": "An account with this email already exists."})
    partner = Partner(**data, user=user, created_by=user, status=Partner.Status.REGISTERED)
    partner.full_clean()
    partner.save()
    PartnerOnboardingHistory.objects.create(partner=partner, actor=user, action="REGISTERED", new_status=partner.status)
    return partner


def review_registration(actor, pk, *, approve):
    from .onboarding import review_onboarding
    return review_onboarding(actor, pk, "approve" if approve else "reject", "" if approve else "Registration rejected by administrator.")


@transaction.atomic
def delete_partner(actor, pk):
    """Delete an unused partner and login together; PROTECT preserves CRM history."""
    from django.shortcuts import get_object_or_404
    require_manager(actor)
    partner = get_object_or_404(Partner.objects.select_for_update(), pk=pk)
    user = User.objects.select_for_update().get(pk=partner.user_id) if partner.user_id else None
    if user and (user.pk == actor.pk or user.role != "PARTNER" or user.is_staff or user.is_superuser):
        raise PermissionDenied
    partner.delete()
    if user:
        user.delete()
